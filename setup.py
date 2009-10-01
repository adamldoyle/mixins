from distutils.core import setup

setup(
    name = 'mixins',
    version = '1.0',
    url = 'http://adamldoyle.com',
    author = 'Adam Doyle',
    author_email = 'adamldoyle@gmail.com',
    description = 'A collection of abstract classes to add a variety of functionality to Django models.',
    license = 'GNU General Public License',
    packages = ['mixins'],
    requires = ['django', 'geopy', 'PIL', 'twitter'],
)