from urllib.parse import parse_qs, unquote

class HandshakeURLBuilder:
    def __init__(self, school_domain: str = "cmu", query_string: str = None):
        """
        school_domain: subdomain for the school (e.g., 'cmu', 'berkeley')
        query_string: optional string like "?jobType=3&per_page=25&page=1"
        """
        self.school_domain = school_domain
        self.params = {
            "page": 1,
            "per_page": 25,
        }
        
        if query_string:
            clean_query = query_string.lstrip("?")
            parsed = parse_qs(clean_query)
            for key, value in parsed.items():
                # flatten single-value lists and decode URL-encoded keys
                self.params[key] = unquote(value[0])


    def set_school(self, school_domain: str):
        """Change the school subdomain dynamically."""
        self.school_domain = school_domain
        return self

    def set_param(self, key, value):
        """Set or update a query parameter."""
        self.params[key] = value
        return self

    #Breaks if you try to remove a param that doesn't exist
    def remove_param(self, key):
        """Remove a parameter entirely."""
        if key in self.params:
            del self.params[key]
        return self

    def build(self):
        """Build the full URL string dynamically based on current settings."""
        base = f"https://{self.school_domain}.joinhandshake.com/job-search"
        query_string = "&".join(
            f"{k}={v}" for k, v in self.params.items() if v is not None
        )
        return f"{base}?{query_string}" if query_string else base

    def clone(self):
        """Create a copy of the builder to modify independently."""
        new_builder = HandshakeURLBuilder(self.school_domain)
        new_builder.params = self.params.copy()
        return new_builder

