from django.contrib.sites.models import Site

class DomainMiddleware:
    
    def process_request(self, request):
        """Parse out the subdomain from the request"""
        request.domain = ''
        request.subdomain = ''
        request.main_domain = False
        host = request.get_host().replace('www.', '')
        domain_pieces = host.split('.')
        
        if len(domain_pieces) < 2:
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
        