from setuptools import setup, find_packages
import os

def read_file(filename):
    if os.path.exists(filename):
        with open(filename, encoding="utf-8") as f:
            return f.read()
    return ""

setup(
    name='ormysql',
    version='0.1.5',
    description='MySQL ORM',
    long_description=read_file("README.md") + "\n\n" + read_file("CHANGELOG.md"),
    long_description_content_type='text/markdown',
    author='Vsevolod Krasovskyi',
    author_email='sevakrasovskiy@gmail.com',
    url='https://github.com/VsevolodKrasovskyi/mysql-orm-lite',
    license='MIT',
    packages=find_packages(),
    install_requires=[
        'aiomysql',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
