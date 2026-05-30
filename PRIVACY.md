# Privacy notes

This application is intentionally minimal:

- it does not ask for names, email addresses, or account details;
- it does not write answers to files or databases;
- the first partner's answers are kept temporarily in the current Streamlit session only;
- after comparison, the original first-partner answer dictionary is cleared;
- hidden form-widget values are removed from session state after each handover;
- only mutual matches are displayed.

## Important limitation

This is a privacy-conscious interface, not a cryptographic anonymity system. When deployed to a remote host, temporary session data is processed in the server memory of that host. Hosting infrastructure may also keep operational logs outside this application's control. For the most private usage, run the app locally on a trusted computer and close the browser tab after resetting the session.

Do not add analytics, tracking pixels, external form services, logging of form values, or persistent storage without clearly notifying users and obtaining appropriate consent.
