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

def render_with_context(request, url, vars):
    from django.template import RequestContext
    from django.shortcuts import render_to_response
    return render_to_response(url, vars, context_instance=RequestContext(request))

def list_page(request, model, subset, template_name='mixins/list_page.html', **kwargs):
    app_label = model._meta.app_label
    model_name = model._meta.verbose_name
    model_name_plural = plural(model._meta.verbose_name)
    if callable(subset):
        subset = subset(kwargs)
    autosuggest_params = kwargs.get('autosuggest_params', {})
    if callable(autosuggest_params):
        autosuggest_params = autosuggest_params(kwargs)
    top_objects = subset.globals().top_ten()
    voteless_objects = subset.globals().voteless()
    title = kwargs.get('title', 'List')
    print template_name
    kwargs.update({'title': title, 'app_label': app_label, 'model_name': model_name, 'model_name_plural': model_name_plural, 'top_objects': top_objects, 'voteless_objects': voteless_objects, 'autosuggest_params': autosuggest_params})
    return render_with_context(request, template_name, kwargs)

def smart_truncate(content, length=100, suffix='...'):
    if len(content) <= length:
        return content
    else:
        return ' '.join(content[:length+1].split(' ')[0:-1]) + '...'

def frac2dec(value):
    value = str(value)
    pieces = value.split(' ')
    try:
        if len(pieces) == 1:
            pieces2 = value.split('/')
            if len(pieces2) == 1:
                return value
            else:
                return float(pieces2[0])/float(pieces2[1])
        else:
            pieces2 = pieces[1].split('/')
            return float(pieces[0]) + float(pieces2[0])/float(pieces2[1])
    except ValueError:
        return value
    
def dec2frac(value, approx=False):
    value = str(value)
    pieces = value.split('.')
    final = pieces[0]
    if float(pieces[1]) == 0:
        return pieces[0]
    for num in range(1,32):
        num = float(num)
        for den in range(int(num)+1,33):
            den = float(den)
            if float(".%s" % (pieces[1])) == num/den:
                if float(final) == 0:
                    return u"%d/%d" % (num, den)
                else:
                    return u"%s %d/%d" % (final, num, den)
    if approx:
        return dec2fracapprox(value)
    else:
        return value

def dec2fracapprox(value):
    value = str(value)
    pieces = value.split('.')
    final = pieces[0]
    if float(pieces[1]) == 0:
        return pieces[0]
    mins = [float("infinity"), 0, 0]
    temp = float(".%s" % (pieces[1]))
    for num in range(1,32):
        num = float(num)
        for den in range(int(num),33):
            den = float(den)
            if abs(num/den - temp) < abs(mins[0] - temp):
                mins = [num/den, num, den]
    if float(final) == 0:
        if mins[2] == 1:
            return u"~%d" % (mins[1])
        else:
            return u"~%d/%d" % (mins[1], mins[2])
    else:
        if mins[2] == 1:
            return u"~%s %d" % (final, mins[1])
        else:
            return u"~%s %d/%d" % (final, mins[1], mins[2])

def remove_excess_white(sentence):
    pieces = sentence.strip().split(" ")
    while '' in pieces:
        pieces.remove('')
    return ' '.join(pieces)

def remove_asterices(sentence):
    return sentence.replace('*', '')

def rules(type, language):
    for line in eval('%sRules_%s' % (type, language)):
        pattern, search, replace = line
        yield lambda word: re.search(pattern, word) and re.sub(search, replace, word)   

def searchRules(noun, type, language):
    for applyRule in rules(type, language):
        result = applyRule(noun)
        if result: return result

def plural(noun, language='en', value=2):
    try:
        if float(value) != 1:
            return searchRules(noun, 'plural', language)
    except ValueError:
        pass
    return noun

def singular(noun, language='en'):
    return searchRules(noun, 'singular', language)

pluralRules_en = [['^(sheep|deer|fish|moose|aircraft|series|haiku|large|small|medium)$', '$', ''],
                  ['(pot|tom)ato$', '$', 'es'],
                  ['[[ml]ouse$', 'ouse$', 'ice'],
                  ['child$', '$', 'ren'],
                  ['booth$', '$', 's'],
                  ['foot$', 'oot$', 'eet'],
                  ['ooth$', 'ooth$', 'eeth'],
                  ['l[eo]af$', 'af$', 'aves'],
                  ['sis$', 'sis$', 'ses'],
                  ['^(hu|ro)man$', '$', 's'],
                  ['man$', 'man$', 'men'],
                  ['^lowlife$', '$', 's'],
                  ['ife$', 'ife$', 'ives'],
                  ['eau$', '$', 'x'],
                  ['^[dp]elf$', '$', 's'],
                  ['lf$', 'lf$', 'lves'],
                  ['[sxz]$', '$', 'es'],
                  ['[^aeioudgkprt]h$', '$', 'es'],
                  ['(qu|[^aeiou])y$', 'y$', 'ies'],
                  ['$', '$', 's']]

singularRules_en = [['^(sheep|deer|fish|moose|aircraft|series|haiku|large|small|medium)$', '$', ''],
                    ['chilies$', 'ies$', 'i'],
                    ['cookies$', 'ies$', 'ie'],
                    ['(pot|tom)atoes$', 'es$', ''],
                    ['[ml]ice$', 'ice$', 'ouse'],
                    ['children$', 'ren$', ''],
                    ['booths$', 's$', ''],
                    ['feet$', 'eet$', 'oot'],
                    ['eeth$', 'eeth$', 'ooth'],
                    ['l[eo]aves$', 'aves$', 'af'],
                    ['ses$', 'ses$', 'sis'],
                    ['^(hu|ro)mans$', 's$', ''],
                    ['men$', 'men$', 'man'],
                    ['^lowlifes$', 's$', ''],
                    ['ives$', 'ives$', 'ife'],
                    ['eaux$', 'x$', ''],
                    ['^[dp]elfs$', 's$', ''],
                    ['lves$', 'lves$', 'lf'],
                    ['[sxz]es$', 'es$', ''],
                    ['[^aeioudgkprt]hes$', 'es$', ''],
                    ['(qu|[^aeiou])ies$', 'ies$', 'y'],
                    ['ss$', '$', ''],
                    ['s$', 's$', ''],
                    ['$', '$', '']]