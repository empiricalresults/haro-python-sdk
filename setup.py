from setuptools import setup, find_packages

if __name__ == '__main__':
    setup(
        name='haro',
        version='2018.4',
        description='Haro.ai Python Library',
        long_description="A thin wrapper for making calls to Haro events and prediction REST API's",
        url="https://github.com/empiricalresults/haro-python-sdk",
        author='Empirical Results Inc.',
        author_email='info@haro.ai',
        license='Apache License Version 2.0, January 2004',
        packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
        install_requires=[
            "six>=1.11.0",
            "requests>=2.18.4",
        ],
        tests_require=[
            'requests-mock==1.4.0',
        ],
        classifiers=[
            "Programming Language :: Python :: 3.5",
            "Programming Language :: Python :: 2.7",
            "Intended Audience :: Developers",
            "Topic :: Scientific/Engineering :: Artificial Intelligence"
        ]
    )
