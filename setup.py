from setuptools import setup, find_packages
import sys, os

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.md')).read()
NEWS = open(os.path.join(here, 'NEWS.txt')).read()


version = '0.0.1'

install_requires = [
    'sfpy',
]

test_requires = [
    'nose',
]

setup(
    name='ieee754fpu',
    version=version,
    description="A nmigen IEEE754 Floating-Point library",
    long_description=README + '\n\n' + NEWS,
    classifiers=[
        "Topic :: Software Development :: Libraries",
        "License :: OSI Approved :: LGPLv3+",
        "Programming Language :: Python :: 3",
    ],
    keywords='nmigen ieee754',
    author='Luke Kenneth Casson Leighton',
    author_email='lkcl@libre-riscv.org',
    url='http://git.libre-riscv.org/?p=ieee754fpu',
    license='GPLv3+',
    packages=find_packages('src'),
    package_dir = {'': 'src'},
    include_package_data=True,
    zip_safe=False,
    install_requires=install_requires,
    tests_require=test_requires,
    test_suite='nose.collector',
)
