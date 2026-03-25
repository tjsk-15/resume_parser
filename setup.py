from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="resume_parser",
    version="0.1.0",
    description="AI-powered resume parsing and summarization for Frappe HRMS Job Applicants",
    author="Tej",
    author_email="tjs.kutnikar@gmail.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
