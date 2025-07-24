# MySQL ORM Lite 

A minimal asynchronous ORM for MySQL built on top of `aiomysql`. Designed for personal projects, but shared in case it helps others.

## Features

- ⚡ Asynchronous work with MySQL via `aiomysql`
- 🧱 Model structure: fields, `PrimaryKey`, `ForeignKey`, etc
- 📦 CRUD operations
- 🧬 Simple migration system
- 🔒 Minimum dependencies, maximum control
- 🛠 The project evolves as and when needed


## 📌 TODO / Planned Features

- [x] **Basic CRUD**  
  Support for asynchronous Create, Read, Update, and Delete operations.

- [x] **Migrations System**  
  Lightweight migration layer that auto-creates tables and tracks schema.

- [x] **Primary / Foreign Keys**  
  Support for `PrimaryKey` and simple `ForeignKey` relationships.

- [ ] **Relation Mapping**  
  Implement intuitive model-to-model relations:
  - `.select_related()`-like join support  
  - automatic model hydration for related fields  
  - lazy/eager loading strategies

- [ ] **Basic Indexing**  
  Allow index definition on fields for optimized querying:
  - support for `INDEX` and `UNIQUE`
  - auto-indexing on primary/foreign keys
  - optional composite indexes

- [ ] **Model-Level Validation**  
  Provide declarative validation rules (e.g. `min_length`, `nullable`, `max_value`).

- [ ] **Logging of SQL Queries**  
  Log raw SQL for debugging and transparency.

- [ ] **CLI Interface**  
  Simple CLI for:
  - applying/reverting migrations  
  - inspecting schema  
  - generating boilerplate model files

- [ ] **Improved Error Handling**  
  More informative exception system with context-aware tracebacks.

- [ ] **Testing Utilities**  
  Helpers to set up and teardown in-memory or temporary test databases.
