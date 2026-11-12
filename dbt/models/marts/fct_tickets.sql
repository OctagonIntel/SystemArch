-- Same rows as marts_restricted.fct_tickets, with every classified column hashed.
{{ select_hashed(ref('restricted_fct_tickets'), 'fct_tickets') }}
