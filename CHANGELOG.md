# Changelog

## [0.1.4] - date

### Added
- Field Enum, Set

### Changed

### Fixed
- mysql pool


## [0.1.3] - 2025-08-19
### Added
- Declarative ManyToMany in Meta with lazy resolution. The attribute name defines generated accessors: <name> (targets) and <name>_rel (through + attached target).
- Symmetric M2M support by declaring a second ManyToMany on the other model (e.g., users = ManyToMany("User", through="UserHasProduct")).
- Improved docstrings for DB.session() and DB.transaction() with clear usage examples.

### Changed
- DDL now adds indexes on all ForeignKey columns for faster M2O/M2M lookups.

### Fixed
- M2M FK detection now uses ForeignKey.to_model (instead of a non-existent ref), enabling non-standard FK names in through models.
- ManyToManyManager.all() de-duplicates target IDs (order-preserving) to avoid repeated results when through rows are duplicated.
- Lazy model resolution in M2M prevents early AttributeError when classes are declared in any order.

## [0.1.2] - 2025-08-15
### Added
- Support for `on_delete` / `on_update` arguments in `ForeignKey` with automatic inclusion in generated DDL (`ON DELETE` / `ON UPDATE` clauses).
- New `join()` method in `QueryMixin` to allow easy INNER/LEFT joins between models, merging fields and supporting JOIN clauses in queries.
- `QueryMixin` class created as an abstract base for CRUD and query logic, inherited by `BaseModel`.
- Detailed Python docstrings in Markdown (PyDoc) for all public `QueryMixin` methods for better maintainability and PyPI documentation.
- Automatic table/column prefixing in `WHERE` and `ORDER BY` when performing JOINs to prevent ambiguous column errors.

### Changed
- `migrate.run()` now runs in a transaction: all table creation DDLs are executed inside `START TRANSACTION` / `COMMIT`, with rollback on error.
- `_select_fields()` now generates SQL with aliased column names (`table__column`) to avoid overwriting columns with the same name in `DictCursor`.
- `_map_row()` implemented to map aliased SQL results back to model attributes.

### Fixed
- Alias handling to avoid column name collisions when multiple tables share column names (`id`, `name`, etc.).
- Correctly prefixed table names in `WHERE` and `ORDER BY` clauses when using JOIN.
- Improved `ForeignKey` handling in `generate_create_table()` to include dependencies for migration ordering.

## [0.1.1] - 2025-08-14
- Initial release
