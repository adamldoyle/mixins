from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldError
from django.core.urlresolvers import NoReverseMatch, reverse
from django.db import models
from django.db.models import Q, Sum, Count
from django.db.models.query import QuerySet
from django.template.defaultfilters import slugify
from geopy import geocoders
from mixins.views import *
from PIL import Image
import os
import twitter

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
    admin_manager = models.Manager()
    objects = MixinManager()
    
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
        
class DeleteMixin(BaseMixin):
    """Implements soft deletes which will only be available from the admin section."""
    deleted = models.BooleanField(default=False)
    
    class Meta:
        abstract = True
    
    def delete(self):
        self.deleted = True
        self.save()
        
class GlobalMixin(BaseMixin):
    is_global = models.BooleanField(default=True)
    
    class Meta:
        abstract = True

class DateMixin(BaseMixin):
    """Implement created/modified dates for the model."""
    created_at = models.DateTimeField(editable=False, auto_now_add=True)
    modified_at = models.DateTimeField(editable=False, auto_now=True)
    
    class Meta:
        abstract = True

class IPMixin(models.Model):
    IP = models.IPAddressField()
    
    class Meta:
        abstract = True

class LocationMixin(models.Model):
    """Uses Google geocoder to determine latitude/longitude for model during save."""
    place = models.TextField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    
    class Meta:
        abstract = True
        
    def save(self):
        if self.place != '':
            g = geocoders.Google('ABQIAAAAYksysDw0in8NRjwEFBJXaxTlfjA2irq0rOHwKfqbHkNeo2dq3RQJjhlAeJUpxWojw0yxWl099pfJvQ')
            self.place, (self.latitude, self.longitude) = g.geocode(self.place)
        super(LocationMixin, self).save()

class SlugMixin(models.Model):
    """Add a slug field based on a certain field.

    Variables to be set in extending model:
        uniqueSlug: if True, will force unique slugs for the model (append _# if conflict)
        slugNewOnly: if True, will only create slug for new instance
        slugValue: string value of field to use for slug
    """
    slug = models.SlugField(editable=False)
    uniqueSlug = False
    slugNewOnly = False
    
    class Meta:
        abstract = True
    
    def save(self):
        if not slugNewOnly or not self.id:
            try:
                if self.uniqueSlug:
                    self.slug = SlugifyUniquely(getattr(self, self.slugValue), self.__class__)
                else:
                    self.slug = slugify(getattr(self, self.slugValue))
            except AttributeError:
                print "Need to define slugValue for main class."
        super(SlugMixin, self).save()

class UserMixin(models.Model):
    
    user = models.ForeignKey(User)
    
    class Meta:
        abstract = True

class UserVote(UserMixin, DateMixin):
    """Contains a single user's vote for any model that extends VoteMixin."""
    vote = models.SmallIntegerField()
    
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey()
    
    def __unicode__(self):
        return u"%s" % self.vote

class VoteMixin(BaseMixin):
    """Implements ability to track user up/down votes on any instance."""
    votes = generic.GenericRelation(UserVote, related_name="%(class)s_related")
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

class ImageThumbEnum:
    """Enum to handle thumb creation behavior."""
    NORMAL = 0
    SQUARE = 1

class ImageMixin(models.Model):
    """Allows an image to be attached to a model instance.
    
    Creating thumbnails or resizing images requires PIL: http://www.pythonware.com/products/pil/
    """
    image = models.ImageField(upload_to=get_image_path)
    
    class Meta:
        abstract = True
        
    def resize_image(self):
        """If image_max_resolution (w,h) is specified on model, shrink down image to be less than that resolution.""" 
        i_filename = self.image.path
        if os.path.isfile(i_filename):
            image = Image.open(i_filename)
            if image.mode not in ('L', 'RGB'):
                image = image.convert('RGB')
            image.thumbnail(self.image_max_resolution, Image.ANTIALIAS)
            image.save(i_filename)
            
    def create_thumbnail(self):
        """If image_thumb_resolution (w,h) is specified on model, will create a thumbnail with that size.
        
        If image_thumb_enum is set to SQUARE, image will be fit to the exact resolution.  Aspect ratio
        is maintained by taking slices from the edges so thumb won't contain whole image (but will be
        semi-centered).
        """
        i_filename = self.image.path
        t_filename = "%s/tn_%s" % (os.path.dirname(i_filename), os.path.basename(i_filename))
        if os.path.isfile(i_filename) and not os.path.isfile(t_filename):
            image = Image.open(i_filename)
            if image.mode not in ('L', 'RGB'):
                image = image.convert('RGB')
            if hasattr(self, 'image_thumb_enum') and self.image_thumb_enum.SQUARE:
                if image.size[0] > image.size[1]:
                    THUMBNAIL_SIZE = (float("infinity"), self.image_thumb_resolution[1])
                else:
                    THUMBNAIL_SIZE = (self.image_thumb_resolution[0], float("infinity"))
                image.thumbnail(THUMBNAIL_SIZE, Image.ANTIALIAS)
                x_left = (image.size[0] - self.image_thumb_resolution[0]) / 2
                y_top = (image.size[1] - self.image_thumb_resolution[1]) / 2
                region = image.crop((x_left, y_top, x_left + self.image_thumb_resolution[0], y_top + self.image_thumb_resolution[1]))
            else:
                image.thumbnail(self.image_thumb_resolution, Image.ANTIALIAS)
                region = image
            region.save(t_filename)
    
    def thumbnail(self):
        """Return full path to thumbnail for model, or creates it if it doesn't exist."""
        if self.image and hasattr(self, 'image_thumb_resolution'):
            i_filename = self.image.path
            t_filename = "%s/tn_%s" % (os.path.dirname(i_filename), os.path.basename(i_filename))
            if not os.path.isfile(t_filename):
                self.create_thumbnail()
            return '%s/%s' % (self.image_path, os.path.basename(t_filename))
        return None
    
    def save(self):
        new_model = not self.id
        super(ImageMixin, self).save()
        if new_model and self.image:
            if hasattr(self, 'image_thumb_resolution'):
                self.create_thumbnail()
            if hasattr(self, 'image_max_resolution'):
                self.resize_image()
    
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