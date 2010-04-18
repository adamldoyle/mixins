from django import template
import re

register = template.Library()

class ThumbnailNode(template.Node):
    def __init__(self, obj, width, height, type):
        self.obj = template.Variable(obj)
        self.width = template.Variable(width)
        self.height = template.Variable(height)
        self.type = template.Variable(type)
        
    def render(self, context):
        actual_obj = self.obj.resolve(context)
        actual_width = self.width.resolve(context)
        actual_height = self.height.resolve(context)
        actual_type = self.type.resolve(context)
        return actual_obj.thumbnail((actual_width, actual_height), actual_type)

def thumbnail(parser, token):
    try:
        tag_name, obj, width, height, type = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError, "%r tag requires arguments" % token.contents.split()[0]
    return ThumbnailNode(obj, width, height, type)
register.tag('thumbnail', thumbnail)