from setuptools import find_packages, setup


setup(
    name="neuro-logging",
    python_requires=">=3.8",
    url="https://github.com/neuro-inc/neuro-logging",
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
