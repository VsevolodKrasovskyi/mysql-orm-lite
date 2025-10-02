---
layout: home
title: ormysql
hero:
  name: ormysql
  text: Tiny async ORM for MariaDB/MySQL
  tagline: Minimal, fast and straightforward ORM built on top of aiomysql
  actions:
    - theme: brand
      text: Get Started
      link: /guide/get-started
    - theme: alt
      text: API
      link: /api/overview
features:
  - icon: 🔌
    title: Connection Pool
    details: Lazy initialization with optional auto-creation of the database
  - icon: 🧱
    title: Simple Models
    details: Fields, ForeignKey, and M2M sugar via Meta
  - icon: ⚙️
    title: CRUD & Filters
    details: create/filter/get/... with operators __gte/__lte/__like/__in
  - icon: 🔒
    title: Safe
    details: Parameterized queries and whitelisted ORDER BY fields
---

## Installation

```bash
pip install ormysql
```