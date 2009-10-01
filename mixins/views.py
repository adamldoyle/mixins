from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse
from django.template.defaultfilters import slugify
from django.utils import simplejson
from django.utils.html import escape

def autosuggest(request):
    """Accepts a GET request (usually AJAX) and returns a JSON object containing a list of matching instances.
    
    GET keys:
        contenttype: takes form of app__model (required).
        usertext: partial text user has typed in (required).
        field: text to return in result for model.  If not given, will use autosuggest_field from model. One of the two must be present.
        requirebeginning: if True, user text will only be matched against the beginning of the word.
        user_only: limit results to those whose user field matches the current user.
        filter_<model_field>=<filter_value>: filter the results on the provided fields (can provide 0 or more).
        
    Each result in return contains:
        id: id of model.
        value: text for the model to display (e.g. title)
        url: absolute url for model (must implement get_absolute_url on model). 
        
    Will try first to only return global/user matching results, if that fails it'll return all matching.
    """
    results = {'results': []}
    if request.GET.has_key('contenttype') and request.GET.has_key('usertext'):
        try:
            app_label, model = request.GET['contenttype'].split('__')
            ct = ContentType.objects.get(app_label=app_label, model=model)
            usertext = request.GET['usertext']
            field = request.GET.get('field', ct.model_class().autosuggest_field)
            if request.GET.has_key('requirebeginning') and request.GET['requirebeginning']:
                kwargs = { str(field + '__istartswith'): str(usertext) }
            else:
                kwargs = { str(field + '__icontains'): str(usertext) }
            if request.GET.has_key('user_only'):
                kwargs['user'] = request.user
            for key, value in request.GET.iteritems():
                if key.find('filter_') == 0:
                    key = str(key[7:])
                    if value == "None":
                        value = None
                    kwargs[key] = value
            try:
                objects = ct.model_class().objects.filter(**kwargs).globals(request.user)
            except AttributeError:
                objects = ct.model_class().objects.filter(**kwargs)
            for object in objects:
                result_row = {'id': object.id, 'value': str(escape(getattr(object, field))), 'url': object.get_absolute_url()}
                results['results'].append(result_row)
        except ContentType.DoesNotExist:
            pass
    serialized = simplejson.dumps(results)
    return HttpResponse(serialized, mimetype="application/json")

def vote(request):
    """Accepts a GET request (usually AJAX) containing a vote and returns a JSON status response.
    
    GET keys:
        contenttype: takes form of app__model (required).
        id: id of model to be voted on (required).
        vote: 1 for up-vote, -1 for down-vote, 0 to get user's current vote (required).
        
    Return:
        error: 0 if successful, 1 if not.
        value: contain net vote value for instance.
        vote: contains user vote (if GET vote value is 0).
    """    
    response = {}
    value = 0
    error = 1
    if request.GET.has_key('contenttype') and request.GET.has_key('id') and request.GET.has_key('vote'):
        try:
            app_label, model = request.GET['contenttype'].split('__')
            ct = ContentType.objects.get(app_label=app_label, model=model)
            id = request.GET['id']
            v = request.GET['vote']
            obj = ct.model_class().objects.filter(pk=id)
            if obj:
                obj = obj[0]
                if request.user.is_authenticated():
                    if v != '0':
                        obj.vote(request.user, v)
                    else:
                        uservote = obj.userVote(request.user)
                        if uservote is not None:
                            response['vote'] = uservote.vote
                value = obj.voteValue()
                error = 0
        except ContentType.DoesNotExist:
            pass
    response['error'] = error
    response['value'] = value
    serialized = simplejson.dumps(response)
    return HttpResponse(serialized, mimetype="application/json")

def get_image_path(instance, filename):
    """Used by ImageMixin to set path to image based on specified path and filename."""
    return '%s/%s' % (instance.image_path, filename)

def SlugifyUniquely(value, model, slugfield="slug"):
    """Returns a slug on a name which is unique within a model's table

    This code suffers a race condition between when a unique
    slug is determined and when the object with that slug is saved.
    It's also not exactly database friendly if there is a high
    likelyhood of common slugs being attempted.

    A good usage pattern for this code would be to add a custom save()
    method to a model with a slug field along the lines of:

            from django.template.defaultfilters import slugify

            def save(self):
                if not self.id:
                    # replace self.name with your prepopulate_from field
                    self.slug = SlugifyUniquely(self.name, self.__class__)
            super(self.__class__, self).save()

    Original pattern discussed at
    http://www.b-list.org/weblog/2006/11/02/django-tips-auto-populated-fields
    """
    suffix = 1
    potential = base = slugify(value)
    while True:
            if suffix > 1:
                    potential = "-".join([base, str(suffix)])
            if not model.objects.filter(**{slugfield: potential}).count():
                    return potential
            # we hit a conflicting slug, so bump the suffix & try again
            suffix += 1