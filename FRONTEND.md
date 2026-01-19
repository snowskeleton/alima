# Frontend Build System

Alima uses a minimal JavaScript build system for bundling frontend dependencies like Uppy.

## Setup

Install Node.js dependencies:

```bash
npm install
```

## Building

Build the JavaScript bundles:

```bash
npm run build
```

This creates:
- `app/static/js/import.bundle.js` - Uppy upload functionality
- `app/static/js/import.bundle.css` - Uppy styles

## Development

Watch mode (auto-rebuild on file changes):

```bash
npm run watch
```

## Adding New Dependencies

1. Install the package:
   ```bash
   npm install @some/package
   ```

2. Import in your source file (`app/static/js/src/*.js`):
   ```javascript
   import Something from '@some/package';
   ```

3. Build:
   ```bash
   npm run build
   ```

## File Structure

- `package.json` - npm dependencies and build scripts
- `app/static/js/src/` - Source JavaScript files
- `app/static/js/*.bundle.js` - Bundled output (gitignored, built during deployment)

## Deployment

The bundled files are gitignored and built during deployment.

### Docker

The Dockerfile automatically:
1. Installs Node.js
2. Copies `package.json` and `package-lock.json`
3. Runs `npm install`
4. Copies source files
5. Runs `npm run build`

Just build the image normally:
```bash
docker build -t alima .
```

### Manual Deployment

1. Install Node.js 20.x
2. Run `npm install`
3. Run `npm run build`
4. Start the application with `uvicorn`

The bundled files will be created in `app/static/js/`.
