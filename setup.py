from setuptools import setup, find_packages
import sys
import os

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.md')).read()
NEWS = open(os.path.join(here, 'NEWS.txt')).read()


version = '0.0.1'

install_requires = [
    #    'sfpy',
    'ieee754fpu',  # needs to be installed manually from git.libre-soc.org
    'pygdbmi',
    'nmigen-soc',  # install manually from git.libre-soc.org
    'ply',  # needs to be installed manually
    'astor',
]

test_requires = [
    'nose',
]

setup(
    name='soc',
    version=version,
    description="A nmigen-based OpenPOWER multi-issue Hybrid CPU / VPU / GPU",
    long_description=README + '\n\n' + NEWS,
    classifiers=[
        "Topic :: Software Development :: Libraries",
        "License :: OSI Approved :: LGPLv3+",
        "Programming Language :: Python :: 3",
    ],
    keywords='nmigen ieee754 libre-soc soc',
    author='Luke Kenneth Casson Leighton',
    author_email='lkcl@libre-soc.org',
    url='http://git.libre-soc.org/?p=soc',
    license='GPLv3+',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    include_package_data=True,
    zip_safe=False,
    install_requires=install_requires,
    tests_require=test_requires,
    test_suite='nose.collector',
)
