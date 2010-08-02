from django.contrib.sites.models import Site
from django.http import Http404

class DomainMiddleware:
    
    def process_request(self, request):
        """Parse out the subdomain from the request"""
        request.domain = ''
        request.subdomain = ''
        request.main_domain = False
        host = request.get_host().replace('www.', '')
        domain_pieces = host.split('.')
        
        if len(domain_pieces) <= 2:
            domain = host.strip()
            subdomain = ''
        else:
            domain = '.'.join(domain_pieces[1:]).strip()
            subdomain = domain_pieces[0].strip()
        
        if Site.objects.get_current().domain == domain:
            request.subdomain = subdomain
            if subdomain == '':
                request.main_domain = True
        else:
            request.domain = host
        
class LockdownMiddleware:

    def process_view(self, request, *args, **kwargs):
        if not "/admin/" in request.META['PATH_INFO'] and not request.user.is_staff:
            raise Http404
        return None

