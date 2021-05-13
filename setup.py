from setuptools import find_packages, setup


setup(
    name="platform-logging",
    python_requires=">=3.7.0",
    url="https://github.com/neuro-inc/platform-logging",
    packages=find_packages(),
    setup_requires=["setuptools_scm"],
    install_requires=[
        "aiohttp>=3.0",
        "aiozipkin",
        "sentry-sdk",
    ],
    use_scm_version=True,
    include_package_data=True,
)
