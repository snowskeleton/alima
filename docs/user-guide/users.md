# User Management

Manage users and invitations in Alima.

## User Roles

Alima has two user roles:

### Admin
- Full access to all features
- Can invite users
- Can manage other users
- Can access server settings
- Can add Audible accounts

### User
- Can browse library
- Can create RSS feeds
- Can download audiobooks
- Cannot invite users
- Cannot access admin features

## Inviting Users

1. Navigate to **Admin → Users**
2. Click **Send Invite**
3. Enter the user's email address
4. Select their role (User or Admin)
5. Click **Send Invite**

The user will receive an email with a registration link.

!!! info "Email Required"
    Email must be configured in **Server Settings** to send invites. Otherwise, you'll see the invite URL in the application logs.

## Pending Invitations

The Users page shows all pending invitations:

- Email address
- Role
- Sent date
- Expiration date
- Status (Active/Expired)

### Revoking Invitations

To revoke an invitation:

1. Find the invitation in the Pending Invitations section
2. Click **Revoke**
3. Confirm the action

The invitation link will no longer work.

## Managing Users

### Viewing Users

The Users page shows:

- Email address
- Role
- Created date
- Last login
- Actions

### Sorting Users

Use the sort dropdown to organize users by:

- Newest First / Oldest First
- Email (A-Z / Z-A)
- Role (A-Z / Z-A)
- Last Login (Recent / Oldest)

### Changing User Roles

To change a user's role:

1. Find the user in the list
2. Click **Change Role**
3. Select the new role
4. Click **Confirm**

### Deleting Users

To remove a user:

1. Find the user in the list
2. Click **Delete**
3. Confirm the deletion

!!! warning
    Deleting a user removes:

    - Their account
    - Their sessions
    - Their RSS feeds
    - Their Audible accounts

    But NOT:

    - Downloaded audiobooks (they remain in the library)

## User Registration

### First User

The first user to register automatically becomes an admin. No invitation is required.

Access registration at: http://localhost:8000/auth/register

### Subsequent Users

After the first user is created, all new users must be invited by an admin. The registration page is no longer accessible directly.

### Accepting Invitations

When a user receives an invitation:

1. They click the link in the email
2. They're taken to the registration page
3. They create a password
4. Their account is created with the invited role

## Self-Service Features

### Changing Password

!!! info "Coming Soon"
    Password change functionality is planned for a future release.

Currently, users must be deleted and re-invited to change passwords.

### Profile Settings

!!! info "Coming Soon"
    User profile settings are planned for a future release.

## Sessions

User sessions last 7 days by default (configurable in `.env`).

Sessions are automatically cleaned up when:

- The user logs out
- The session expires
- The user is deleted

## Security

### Password Requirements

Passwords must be:

- At least 8 characters long

!!! tip
    We recommend using a password manager to generate strong, unique passwords.

### Session Security

- Sessions use secure, signed cookies
- CSRF protection on all forms
- Sessions are invalidated on logout
- Expired sessions are automatically cleaned up

## Troubleshooting

### Can't Send Invites

Check that email is configured:

1. Go to **Admin → Server Settings**
2. Configure SMTP settings
3. Click **Send Test Email** to verify

### Invite Email Not Received

- Check spam folder
- Verify email address is correct
- Check server logs for send errors
- Try the "Send Test Email" feature

### User Can't Register

Common issues:

- Invitation has expired (check Pending Invitations)
- Invitation was revoked
- User already has an account with that email
- Email link was corrupted (missing characters)

### Forgot Password

Currently, there's no password reset feature. Options:

1. Admin deletes the user account
2. Admin sends a new invitation
3. User creates a new account with the same email
