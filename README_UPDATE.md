# Warehouse Management System — extended update

## Added modules
- Supplier and customer master data
- Product barcode, category, unit of measure, reorder level and lead time
- Warehouse location hierarchy and product-to-location balances
- Stock adjustment approval and audit logs
- Stock transfer requests with manager completion and source/destination quantity updates
- Customer order header and order lines, cancellation, and ordered-quantity validation during picking
- Cycle counts with manager reconciliation
- Customer/supplier returns with restock, quarantine and supplier-dispatch decisions
- Product batch/expiry records; receiving can be linked to a supplier record, batch and structured putaway location
- Staff role assignment screen
- Inventory CSV export

## Setup
1. Back up your database and source code.
2. Activate the project's virtual environment.
3. Run `python manage.py migrate`.
4. Run `python manage.py check`.
5. Run `python manage.py test accounts`.
6. Run `python manage.py runserver`.

Create a manager/admin account with Django admin (`python manage.py createsuperuser`). The stock-transfer, cycle-count reconciliation and return-review buttons require a staff/manager account. Configure `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and `DATABASE_URL` through environment variables for deployment.

## Important operational notes
- Transfers require an existing source ProductLocation balance; this prevents moving stock that is not recorded at the source.
- Cycle-count reconciliation uses the recorded expected quantity and applies the count variance to the product total. Review concurrent activity before reconciliation.
- Batch records are tracked separately from the total product quantity. The application should be validated with real receiving and dispatch procedures before using batch balances as a regulated traceability ledger.
- Supplier carrier APIs, SMS/email notification providers, ERP/accounting integrations, IoT sensors, route optimization, and automated wave picking require provider credentials and are not connected by this source-only update.
- Back up the database before applying migrations to an existing deployment.
