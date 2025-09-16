from setuptools import setup, find_packages

setup(
    name="scrapinsta",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "beautifulsoup4",
        "selenium",
        "webdriver-manager",
    ],
    author="Tu Nombre",
    author_email="tu.email@ejemplo.com",
    description="Herramienta para scraping de Instagram",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/tu-usuario/scrapinsta",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
) 