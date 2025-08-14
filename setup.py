from setuptools import setup, find_packages

setup(
    name='ormysql',
    version='0.1.1',
    description='MySQL ORM',
    long_description=open('README.md', encoding='utf-8').read(),
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
