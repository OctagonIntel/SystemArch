-- Same rows as marts_restricted.dim_customer, with every classified column hashed.
{{ select_hashed(ref('restricted_dim_customer'), 'dim_customer') }}
