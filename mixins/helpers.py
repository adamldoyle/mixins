from django import template
import re

class VariableNode(template.Node):
    """Provide basic implementation of template Node. Extending class only needs to implement
        setVariable, which should return an object."""
        
    def __init__(self, var_name):
        self.var_name = var_name
    
    """Add the object to the context with the desired variable name."""
    def render(self, context):
        context[self.var_name] = self.setVariable(context)
        return ''
    
    """Extending classes need to override this method."""
    def setVariable(self, context):
        return None
    
def VariableTag(parser, token, varNode):
    """Implementation of the tag, shouldn't need to edit.  varNode is class that extends VariableNode."""
    
    try:
        tag_name, arg = token.contents.split(None, 1)
    except ValueError:
        raise template.TemplateSyntaxError, "%r tag requires arguments" % token.contents.split()[0]
    m = re.search(r'as (\w+)', arg)
    if not m:
        raise template.TemplateSyntaxError, "%r tag had invalid arguments" % tag_name
    var_name = m.group(1)
    return varNode(var_name)