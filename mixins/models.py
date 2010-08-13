from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.core.exceptions import FieldError
from django.core.urlresolvers import NoReverseMatch, reverse
from django.db import models
from django.db.models import Q, Sum, Count
from django.db.models.query import QuerySet
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext as _
from mixins.views import *
import os

class MixinManager(models.Manager):

    """Custom manager to handle mixin queries."""    
    def get_query_set(self):
        """Return custom queryset from BaseMixin model. Filter out deleted instances, if possible."""
        set = self.model.MixinQuerySet(self.model)
        try:
            return set.filter(deleted=False)
        except FieldError:
            return set

class BaseMixin(models.Model):
    """Model to be extended by any mixins requiring custom queries."""
    objects = MixinManager()
    admin_manager = models.Manager()
    
    class MixinQuerySet(QuerySet):
        """Override queryset to allow custom query filters to be chained onto eachother."""
        
        def globals(self, user=None):
            """Return only the instances labeled as global or owned by the user (if specified)."""
            try:
                if user and user.is_authenticated():
                    return self.filter(Q(user=user) | Q(is_global=1))
                else:
                    return self.filter(is_global=1)
            except FieldError:
                return self.all()
        
        def top_n(self, n):
            return self.by_votes()[:n]
        
        def top_ten(self):
            return self.top_n(10)
        
        def by_votes(self):
            """Order the models based on their votes, tie goes to instance with fewest total votes."""
            try:
                query_set = UserVote.objects.filter(content_type=self.model().contenttype().id,
                                                    object_id__in=self.values_list('id', flat=True)
                                                    ).annotate(vote_score=Sum('vote'),
                                                               total_votes=Count('vote')
                                                               ).order_by('-vote_score',
                                                                          'total_votes'
                                                                          ).values('object_id',
                                                                                   'vote_score',
                                                                                   'total_votes')
                query_set.query.group_by = ['object_id']
                ids = [obj['object_id'] for obj in query_set]
                objects = self.select_related().in_bulk(ids)
                return [objects[id] for id in ids]
            except FieldError:
                return self.all()
        
        def voteless(self):
            try:
                return self.filter(~Q(votes__id__gt=0))
            except FieldError:
                return []
        
        def newest(self, num_newest=10):
            return self.by_date()[:num_newest]
            
        def by_date(self):
            try:
                return self.order_by('-created_at')
            except FieldError:
                return self.all()
    
    class Meta:
        abstract = True

class DictionaryField(models.Field):

    __metaclass__ = models.SubfieldBase

    def to_python(self, value):
        if isinstance(value, dict) or value == '':
            return value
        return simplejson.loads(value)
    
    def get_db_prep_value(self, value):
        if value == '':
            return value
        return simplejson.dumps(value)
    
    def get_db_prep_lookup(self, lookup_type, value):
        if lookup_type != 'contains' and lookup_type != 'icontains':
            raise TypeError('Lookup type %r not supported.' % lookup_type)
        elif not isinstance(value, str) and not isinstance(value, unicode) and not isinstance(value, tuple) and not isinstance(value, list) and not isinstance(value, dict):
            raise ValueError('Must pass a string, tuple, list or dictionary.')
        
        if isinstance(value, str) or isinstance(value, unicode):
            return ['%s%s%s' % ('%', value, '%')]
        elif isinstance(value, dict):
            if len(value) != 1:
                raise ValueError('Input must be of length one.')
            return ['%s"%s": "%s"%s' % ('%', value.keys()[0], value[value.keys()[0]], '%')]
        else:
            if len(value) != 2:
                raise ValueError('Input must be of length two.')
            return ['%s"%s": "%s"%s' % ('%', value[0], value[1], '%')]
    
    def get_internal_type(self):
        return 'TextField'

from south.modelsinspector import add_introspection_rules
add_introspection_rules([
    (
        [DictionaryField],
        [],
        {},
    ),
], ["^mixins\.models\.DictionaryField"])
        
class DeleteMixin(BaseMixin):
    """Implements soft deletes which will only be available from the admin section."""
    deleted = models.BooleanField(default=False, db_index=True)
    
    class Meta:
        abstract = True
    
    def delete(self, force=False):
        if force:
            super(DeleteMixin, self).delete()
        else:
            self.deleted = True
            self.save()
        
class GlobalMixin(BaseMixin):
    is_global = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        abstract = True

class DateMixin(BaseMixin):
    """Implement created/modified dates for the model."""
    created_at = models.DateTimeField(editable=False, auto_now_add=True, db_index=True)
    modified_at = models.DateTimeField(editable=False, auto_now=True)
    
    class Meta:
        abstract = True

class IPMixin(models.Model):
    IP = models.IPAddressField()
    
    class Meta:
        abstract = True

class SimpleLocationMixin(models.Model):
    city = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    
    class Meta:
        abstract = True
        
    def simpleAddress(self):
        return ', '.join([field for field in (self.city, self.state) if field != ''])

class LocationMixin(SimpleLocationMixin):
    """Uses Google geocoder to determine latitude/longitude for model during save."""
    address = models.CharField(max_length=100)
    address2 = models.CharField(max_length=100, blank=True)
    zip = models.CharField(max_length=12)
    country = models.CharField(max_length=50, default='US')
    latitude = models.FloatField(default=0)
    longitude = models.FloatField(default=0)
    
    class Meta:
        abstract = True
        
    def buildFullAddress(self):
        full = []
        for field in (self.address, self.address2, self.city, self.state, self.zip):
            if field != '':
                full.append(field)
        partial = ' '.join(full)
        if partial != '':
            return '%s %s' % (partial, self.country)
        return ''
        
    def save(self):
        do_save = True
        if self.address != '':
            try:
                from geopy import geocoders
                g = geocoders.Google('ABQIAAAAYksysDw0in8NRjwEFBJXaxTlfjA2irq0rOHwKfqbHkNeo2dq3RQJjhlAeJUpxWojw0yxWl099pfJvQ')
                addresses = list(g.geocode(self.buildFullAddress(), exactly_one=False))
                if len(addresses) == 1:
                    self.latitude, self.longitude = addresses[0][1]
                else:
                    self.latitude = 0
                    self.longitude = 0
                    self.potential_addresses = addresses
                    #do_save = False
            except ImportError:
                self.latitude = 0
                self.longitude = 0
        if do_save:
            super(LocationMixin, self).save()

class SlugMixin(models.Model):
    """Add a slug field based on a certain field.

    Variables to be set in extending model:
        uniqueSlug: if True, will force unique slugs for the model (append _# if conflict)
        slugNewOnly: if True, will only create slug for new instance
        slugValue: string value of field to use for slug
    """
    slug = models.SlugField(editable=False, db_index=True)
    uniqueSlug = False
    slugNewOnly = False
    
    class Meta:
        abstract = True
    
    def save(self):
        if not self.slugNewOnly or not self.id:
            try:
                if self.uniqueSlug:
                    self.slug = SlugifyUniquely(getattr(self, self.slugValue), self.__class__)
                else:
                    self.slug = slugify(getattr(self, self.slugValue))
            except AttributeError:
                print "Need to define slugValue for main class."
        super(SlugMixin, self).save()

class UserMixin(models.Model):
    
    user = models.ForeignKey(User, null=True, blank=True)
    
    class Meta:
        abstract = True

class Tag(models.Model):
    tag = models.CharField(max_length=20)
    
    def __unicode__(self):
        return self.tag

class TagMixin(models.Model):
    tags = models.ManyToManyField(Tag, null=True, blank=True, related_name="%(class)s_tags")
    
    class Meta:
        abstract = True

class UserVote(UserMixin, DateMixin):
    """Contains a single user's vote for any model that extends VoteMixin."""
    vote = models.SmallIntegerField(db_index=True)
    
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey()
    
    def __unicode__(self):
        return u"%s" % self.vote

class VoteMixin(BaseMixin):
    """Implements ability to track user up/down votes on any instance."""
    votes = generic.GenericRelation(UserVote, related_name="%(class)s_votes")
    uservote = None
    votevalue = None
    
    class Meta:
        abstract = True
    
    def vote(self, user, vote):
        """Cast up/down vote for user."""
        if int(vote) != - 1 and int(vote) != 1:
            return
        try:
            old_vote = self.votes.filter(user=user)[0]
            old_vote.vote = vote
            old_vote.save()
        except IndexError:
            self.votes.create(vote=vote, user=user)
    
    def userVote(self, user):
        """Returns the user's vote for the instance."""
        try:
            self.uservote = self.votes.filter(user=user)[0]
        except IndexError:
            self.uservote = None
        return self.uservote
    
    def voteUps(self):
        """Return all up-votes for instance."""
        return self.votes.filter(vote=1)
    
    def voteUpCount(self):
        """Return total number of up-votes for instance."""
        return self.voteUps().count()
    
    def voteDowns(self):
        """Return all down-votes for instance."""
        return self.votes.filter(vote= - 1)
    
    def voteDownCount(self):
        """Return total number of down-votes for instance."""
        return self.voteDowns().count()
    
    def voteValue(self):
        """Returns the net vote value for instance."""
        self.votevalue = self.voteUpCount() - self.voteDownCount()
        return self.votevalue
    
    def clearVotes(self):
        self.votes.all().delete()
    
    def contenttype(self):
        """Helper method to get the contenttype for the model."""
        return ContentType.objects.get_for_model(self)

class Comment(UserMixin, DateMixin, VoteMixin):
    """Contains a single users comment for any model that extends CommentMixin.""" 
    comment = models.TextField()
    
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey()
    
    class Meta:
        ordering = ('-created_at',)
    
    def __unicode__(self):
        return u"%s" % self.comment

class CommentMixin(models.Model):
    """Allow commenting on any model instance."""
    
    comments = generic.GenericRelation(Comment)
    
    class Meta:
        abstract = True

class AutosuggestMixin(models.Model):
    """Allow model to be searched using autosuggest. Change autosuggest_field from default of 'title' if need be."""
    autosuggest_field = 'title'
    
    class Meta:
        abstract = True

try:
    import twitter
    class TwitterMixin(models.Model):
        """Send a tweet whenever the implementer decides.
        
        Requires python wrapper for Twitter API: http://code.google.com/p/python-twitter/
        
        Extending model must implement method twitter_message which takes no params and returns
        a 140 character string to tweet.  It doesn't matter what's in it, which is why no implementation
        is provided.
        
        Settings to be placed in settings.py:
            TWEETING: if True, tweets will be sent
            TWITTER_USERNAME
            TWITTER_PASSWORD
        """
        
        class Meta:
            abstract = True
            
        def tweet(self):
            if not settings.TWEETING:
                return
            username = settings.TWITTER_USERNAME
            password = settings.TWITTER_PASSWORD
            message = self.twitter_message()
            api = twitter.Api(username, password)
            try:
                api.PostUpdate(message)
            except ValueError:
                pass
except ImportError:
    class TwitterMixin(models.Model):
        pass

class ImageThumbEnum:
    """Enum to handle thumb creation behavior."""
    NORMAL = 0
    FIT = 1

IMAGE_STYLE_CHOICES = (
    (ImageThumbEnum.NORMAL, _("Don't crop to fit")),
    (ImageThumbEnum.FIT, _('Crop to fit')))

class ImageMixin(models.Model):
    """Allows an image to be attached to a model instance.
    
    Creating thumbnails or resizing images requires PIL: http://www.pythonware.com/products/pil/
    """
    image = models.ImageField(upload_to=get_image_path, null=True, blank=True)
    
    class Meta:
        abstract = True
        
    def resize_image(self, resolution):
        try:
            from PIL import Image
            """If image_max_resolution (w,h) is specified on model, shrink down image to be less than that resolution.""" 
            i_filename = self.image.path
            if os.path.isfile(i_filename):
                image = Image.open(i_filename)
                if image.mode not in ('L', 'RGB'):
                    image = image.convert('RGB')
                image.thumbnail(resolution, Image.ANTIALIAS)
                image.save(i_filename)
        except ImportError:
            pass
            
    def create_thumbnail(self, resolution, type):
        """If image_thumb_resolution (w,h) is specified on model, will create a thumbnail with that size.
        
        If image_thumb_type is set to SQUARE, image will be fit to the exact resolution.  Aspect ratio
        is maintained by taking slices from the edges so thumb won't contain whole image (but will be
        semi-centered).
        """
        try:
            from PIL import Image
            i_filename = self.image.path
            t_filename = "%s/tn_%sx%s_%s_%s" % (os.path.dirname(i_filename), resolution[0], resolution[1], type, os.path.basename(i_filename))
            if os.path.isfile(i_filename) and not os.path.isfile(t_filename):
                image = Image.open(i_filename)
                if image.mode not in ('L', 'RGB'):
                    image = image.convert('RGB')
                if type == ImageThumbEnum.FIT:
                    if (float(image.size[0]) / float(image.size[1])) > (float(resolution[0]) / float(resolution[1])):
                        THUMBNAIL_SIZE = (float("infinity"), resolution[1])
                    else:
                        THUMBNAIL_SIZE = (resolution[0], float("infinity"))
                    image.thumbnail(THUMBNAIL_SIZE, Image.ANTIALIAS)
                    x_left = (image.size[0] - resolution[0]) / 2
                    y_top = (image.size[1] - resolution[1]) / 2
                    region = image.crop((x_left, y_top, x_left + resolution[0], y_top + resolution[1]))
                else:
                    image.thumbnail(resolution, Image.ANTIALIAS)
                    region = image
                region.save(t_filename)
        except ImportError:
            pass
    
    def thumbnail(self, resolution=None, type=ImageThumbEnum.NORMAL):
        """Return full path to thumbnail for model, or creates it if it doesn't exist."""
        if resolution is None and hasattr(self, 'image_thumb_resolution'):
            resolution = self.image_thumb_resolution
        if self.image and resolution is not None:
            i_filename = self.image.path
            t_filename = "%s/tn_%sx%s_%s_%s" % (os.path.dirname(i_filename), resolution[0], resolution[1], type, os.path.basename(i_filename))
            if not os.path.isfile(t_filename):
                self.create_thumbnail(resolution, type)
            if not os.path.isfile(t_filename):
                return None
            else:
                return '%s/%s' % (os.path.dirname(self.image.url), os.path.basename(t_filename))
        return None
    
    def new_image(self):
        has_changed = False
        if not self.id:
            has_changed = True
        else:
            try:
                old = self.__class__.objects.get(pk=self.id)
                if not old.image or old.image.path != self.image.path:
                    has_changed = True
            except self.__class__.DoesNotExist:
                has_changed = True
        return has_changed
    
    def save(self):
        has_changed = self.image and self.new_image()
        super(ImageMixin, self).save()
        if self.image and has_changed:
            if hasattr(self, 'image_thumb_resolution'):
                type = ImageThumbEnum.NORMAL
                if hasattr(self, 'image_thumb_type'):
                    type = self.image_thumb_type
                self.create_thumbnail(self.image_thumb_resolution, type)
            if hasattr(self, 'image_max_resolution'):
                self.resize_image(self.image_max_resolution)

class DomainMixin(models.Model):
    domain = models.CharField(max_length=40, null=True, blank=True)
    subdomain = models.CharField(max_length=30, unique=True)
    
    class Meta:
        abstract=True
    
    def get_domain(self, force_subdomain=False):
        if self.domain and not force_subdomain:
            return 'http://%s' % self.domain
        else:
            return 'http://%s.%s' % (self.subdomain, Site.objects.get_current().domain)

class EmailMixin(models.Model):
    email = models.CharField(max_length=320, null=True, blank=True)
    
    class Meta:
        abstract=True
    
class UserVoteAdmin(admin.ModelAdmin):
    """Show admin page for user votes which includes links back to the model instance's change page."""
    list_display = ('vote', 'user', 'model_link', 'content_object_link')

    def model_link(self, obj):
        return '%s.%s' % (obj.content_type.app_label, obj.content_type)
    model_link.short_description = 'Model'

    def content_object_link(self, obj):
        try:
            url = reverse('admin:%s_%s_change' % (obj.content_type.app_label, obj.content_type.name), args=(obj.object_id,))
            return '<a href="%s">%s</a>' % (url, obj.content_object)
        except NoReverseMatch:
            return obj.content_object
    content_object_link.allow_tags = True
    content_object_link.short_description = 'Object'

admin.site.register(UserVote, UserVoteAdmin)