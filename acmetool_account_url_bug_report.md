# Bug Report: Let's Encrypt Account URL Not Being Retrieved for `cmdeploy dns`

## Issue Description

The `cmdeploy dns` command fails with the error message "could not get letsencrypt account url, please run 'cmdeploy run'" even after successfully running `cmdeploy run`. This occurs because the command relies on `acmetool account-url` to retrieve the Let's Encrypt account URL, but this command sometimes fails to return the URL despite the account being properly set up and the URL file existing on the file system.

## Steps to Reproduce

1. Deploy a new server using `cmdeploy run` (which successfully completes)
2. Verify that Let's Encrypt certificates are properly generated (visible in `/var/lib/acme/`)
3. Run `cmdeploy dns` to configure DNS settings
4. Observe the error: "could not get letsencrypt account url, please run 'cmdeploy run'"
5. Manually check that the account URL file exists with: `cat /var/lib/acme/accounts/acme-v02.api.letsencrypt.org%2fdirectory/*/url`

## Expected vs. Actual Behavior

**Expected behavior**: 
- After a successful `cmdeploy run`, the `cmdeploy dns` command should retrieve the Let's Encrypt account URL from the system and use it to generate proper DNS configuration instructions.

**Actual behavior**:
- The `cmdeploy dns` command fails with "could not get letsencrypt account url, please run 'cmdeploy run'" even though:
  - The `cmdeploy run` command completed successfully
  - The Let's Encrypt account URL file exists at `/var/lib/acme/accounts/acme-v02.api.letsencrypt.org%2fdirectory/*/url`
  - The URL can be read manually using `cat`
  - The `acmetool account-url` command fails to return the URL (returns empty string)

## Root Cause

The `acmetool account-url` command sometimes doesn't properly read the URL file despite the file being present and readable. The `rdns.py` script only used this command to retrieve the URL with no fallback mechanism.

## Solution Implemented

Added a fallback method in `rdns.py` that directly reads the URL file from the filesystem when the `acmetool account-url` command fails:

```python
def get_acme_account_url():
    """Get the acmetool account URL with fallback methods.
    
    First tries the acmetool command, then falls back to searching the filesystem
    if the command fails or returns empty.
    """
    # Try the acmetool command first
    acme_url = shell("acmetool account-url", fail_ok=True)
    if acme_url:
        return acme_url
    
    # Fallback: search for URL files in acme accounts directory
    try:
        acct_base = "/var/lib/acme/accounts/"
        # Find Let's Encrypt directory
        le_dirs = glob.glob(os.path.join(acct_base, "*letsencrypt*"))
        if not le_dirs:
            return ""
        
        # Find account directories
        for le_dir in le_dirs:
            acct_dirs = glob.glob(os.path.join(le_dir, "*"))
            for acct_dir in acct_dirs:
                url_file = os.path.join(acct_dir, "url")
                if os.path.isfile(url_file):
                    # Read the URL file content
                    with open(url_file, "r") as f:
                        url = f.read().strip()
                        if url:
                            return url
    except Exception:
        # Any exception during fallback should be ignored
        pass
    
    return ""
```

Then updated the `perform_initial_checks` function to use this new function:

```python
res["acme_account_url"] = get_acme_account_url()
```

## Testing Notes

After implementing the fix:
1. The `cmdeploy dns` command now successfully retrieves the Let's Encrypt account URL even when the `acmetool account-url` command fails
2. The command correctly generates all required DNS entries, including the CAA record with the proper account URL
3. The fix is robust against potential errors in filesystem operations by wrapping the fallback in a try-except block
4. The solution maintains backward compatibility by first trying the original method before falling back to the direct file reading

## Additional Information

This bug may affect both new deployments and existing deployments where the `acmetool` command isn't functioning properly. The fix ensures that DNS configuration can proceed even in cases where there might be issues with the `acmetool` command-line utility.

## Affected Files

- `cmdeploy/src/cmdeploy/remote/rdns.py`

