-- marts_restricted.dim_employee with personal data hashed
{{ select_hashed(ref('restricted_dim_employee'), 'dim_employee') }}
