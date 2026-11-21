# Test workflow

1. Sign in as an administrator or manager.
2. Open **Staff roles**, then choose **Create employee**.
3. Assign one or more employee roles.
4. Login with the employee account.
5. Receive goods using a product name and SKU.
6. In Putaway, select a good-condition received good and assign a storage location.
7. Inventory updates after putaway.
8. Create a picking task using the exact product name and SKU.
9. The system checks available stock and subtracts the picked quantity.
10. Pack the picked quantity and ship it to a destination.

## Creating employees and assigning roles

Public registration is disabled. Only Django superusers/staff and users with the **Administrator** or **Warehouse manager** role can create employees from **Staff roles -> Create employee**.

An employee may have multiple roles. The employee receives the combined access permissions of all selected roles. Employees default to no roles unless at least one role is selected.
