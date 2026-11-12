-- Same rows as marts_restricted.dim_employee, with every classified column hashed.
{{ select_hashed(ref('restricted_dim_employee'), 'dim_employee') }}
