# Inventory DB Setup

Retriever Inventory uses the existing `retriever_inventory` MySQL schema from
the old Retriever app. It is not part of the normal `retriever_core` migration
stream because production may use a different MySQL user or grants for that
schema.

Production needs one of these:

- grant the main `MYSQL_USER` access to `retriever_inventory`; or
- set `INVENTORY_MYSQL_USER` and `INVENTORY_MYSQL_PASSWORD` in
  `D:\retriever-rebuild\env\retriever.env` for a MySQL user that can read/write
  `retriever_inventory`.

Optional overrides:

```text
INVENTORY_MYSQL_DATABASE=retriever_inventory
INVENTORY_MYSQL_HOST=
INVENTORY_MYSQL_PORT=
INVENTORY_MYSQL_USER=
INVENTORY_MYSQL_PASSWORD=
```

If the schema ever needs to be created fresh, use the old Retriever reference
schema at:

```text
projects/Retriever/migrations/retriever_inventory_schema.sql
```
