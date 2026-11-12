-- marts_restricted.dim_customer with personal data hashed
{{ select_hashed(ref('restricted_dim_customer'), 'dim_customer') }}
