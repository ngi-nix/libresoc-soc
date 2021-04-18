from setuptools import setup, find_packages
import sys
import os

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.md')).read()
NEWS = open(os.path.join(here, 'NEWS.txt')).read()


version = '0.0.1'

# using pip3 for ongoing development is a royal pain.  seriously not
# recommended.  therefore a number of these dependencies have been
# commented out.  *they are still required* - they will need installing
# manually.

install_requires = [
    #    'sfpy',    # needs manual patching
    'ieee754fpu',   # uploaded (successfully, whew) to pip
    'pygdbmi',      # safe to include
    # 'nmigen-soc', # install manually from git.libre-soc.org
    # 'ply',        # needs to be installed manually
    'astor'         # safe to include
]

test_requires = [
    'nose',
    # install pia from https://salsa.debian.org/Kazan-team/power-instruction-analyzer
    'power-instruction-analyzer'
]

setup(
    name='libresoc',
    version=version,
    description="A nmigen-based OpenPOWER multi-issue Hybrid CPU / VPU / GPU",
    long_description=README + '\n\n' + NEWS,
    classifiers=[
        "Topic :: Software Development",
        "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)",
        "Programming Language :: Python :: 3",
    ],
    keywords='nmigen ieee754 libre-soc soc',
    author='Luke Kenneth Casson Leighton',
    author_email='lkcl@libre-soc.org',
    url='http://git.libre-soc.org/?p=soc',
    license='LGPLv3+',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    include_package_data=True,
    zip_safe=False,
    install_requires=install_requires,
    tests_require=test_requires,
    test_suite='nose.collector',
)
