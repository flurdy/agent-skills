# EAS Build Error - View latest build status and errors

Show the status and errors from the latest EAS build.

## Usage

```
/eas-build-error              # Latest build (any platform)
/eas-build-error ios           # Latest iOS build
/eas-build-error android       # Latest Android build
/eas-build-error <build-id>    # Specific build by ID
```

## Implementation

### Step 1: Get the build

Parse the argument to determine what to fetch:

- If argument looks like a UUID (contains hyphens, 36 chars): treat as build ID
  ```bash
  npx eas build:view <build-id> --json
  ```
- If argument is `ios` or `android`: filter by platform
  ```bash
  npx eas build:list --limit=1 --platform=<platform> --json --non-interactive
  ```
- If no argument: get latest build across all platforms
  ```bash
  npx eas build:list --limit=1 --json --non-interactive
  ```

### Step 2: Display build summary

From the JSON output, extract and display:

```
## EAS Build: <STATUS>

| Field       | Value                          |
|-------------|--------------------------------|
| ID          | <id>                           |
| Platform    | <platform>                     |
| Profile     | <buildProfile>                 |
| Status      | <status> (with emoji: ✓/✗/⏳)  |
| Commit      | <gitCommitHash> <gitCommitMessage> |
| Started     | <createdAt>                    |
| Duration    | <computed from metrics>        |
| Logs        | <link to expo.dev>             |
```

### Step 3: Show errors (if build failed)

If `status` is `ERRORED` or `CANCELED`:

1. **Show the error field** from the JSON:
   ```
   ### Error
   <error.message>
   ```

2. **Fetch detailed logs** — try each URL in `logFiles` array:
   - Use `WebFetch` on each log URL
   - Extract error lines, warnings, and failure details
   - If URLs return 404 (expired), note that logs have expired

3. **Try xcode build logs** if available:
   - Check `artifacts.xcodeBuildLogsUrl`
   - Fetch and extract compilation errors

4. **If all log URLs have expired**, tell the user:
   ```
   Log URLs have expired (15-minute TTL).
   View full logs at: <expo.dev link>
   ```

### Step 4: Suggest fixes (if applicable)

If you recognize common error patterns, suggest fixes:

| Error Pattern | Suggestion |
|---|---|
| `non-modular header inside framework module` | Add `CLANG_ALLOW_NON_MODULAR_INCLUDES_IN_FRAMEWORK_MODULES` to post_install |
| `module map file not found` | Check `use_modular_headers!` vs `use_frameworks!` in Podfile |
| `Swift pods cannot yet be integrated as static libraries` | Add `useFrameworks: "static"` to expo-build-properties |
| `Pod install` errors | Check CocoaPods compatibility, try `pod repo update` |
| `No signing certificate` | Check EAS credentials with `eas credentials` |
| `Provisioning profile` | Run `eas credentials` to fix provisioning |

## Example Output

```
## EAS Build: ERRORED ✗

| Field    | Value                                                    |
|----------|----------------------------------------------------------|
| ID       | 6a50d5ae-6a62-1345-96d3-c1def3755cf1                     |
| Platform | iOS                                                      |
| Profile  | development                                              |
| Status   | ✗ ERRORED                                                |
| Commit   | 8a2ba05 feat: Add haptic feedback...                      |
| Duration | 94s                                                      |
| Logs     | https://expo.dev/accounts/USERNAME/projects/expire/builds/… |

### Error
The "Run fastlane" step failed because of an error in the Xcode build process.

### Detected Errors
- module map file 'gRPC-Core.modulemap' not found (in target 'gRPC-C++')

### Suggested Fix
The `use_modular_headers!` setting is breaking gRPC module maps.
Consider using `useFrameworks: "static"` with a post_install hook instead.
```
