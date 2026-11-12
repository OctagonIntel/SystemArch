-- marts_restricted.fct_tickets with personal data hashed
{{ select_hashed(ref('restricted_fct_tickets'), 'fct_tickets') }}
