from setuptools import find_packages, setup


setup(
    name="platform-logging",
    python_requires=">=3.6.0",
    url="https://github.com/neuromation/platform-logging",
    packages=find_packages(),
    setup_requires=["setuptools_scm"],
    use_scm_version=True,
    package_data={"platform_logging": ["py.typed"]},
    include_package_data=True,
)
