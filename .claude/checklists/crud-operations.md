# CRUD Operations Checklist

Domain-specific validation rules for Create/Read/Update/Delete features.

## Rules

- Create and edit operations use the same modal or form component
- Page loads correctly on browser refresh (no stale state)
- Data persists after save and is correct on reload
- Cancel discards unsaved changes without saving
- Save button enables only when all required fields are filled
- Validation errors display inline near the relevant field
- Delete requires a confirmation dialog before executing
