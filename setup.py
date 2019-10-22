from setuptools import find_packages, setup


install_requires = ["PyYAML==5.1.2"]

setup(
    name="platform-logging",
    python_requires=">=3.6.0",
    url="https://github.com/neuromation/platform-logging",
    install_requires=install_requires,
    packages=find_packages(),
    setup_requires=["setuptools_scm"],
    use_scm_version=True,
)
