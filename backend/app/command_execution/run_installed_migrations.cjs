'use strict';

const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');

const [packageName, fromVersion, toVersion] = process.argv.slice(2);
const packagePattern = /^@?[A-Za-z0-9][A-Za-z0-9._-]*(?:\/[A-Za-z0-9][A-Za-z0-9._-]*)?$/;
const versionPattern = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;
if (!packageName || !packagePattern.test(packageName) ||
    !versionPattern.test(fromVersion || '') || !versionPattern.test(toVersion || '')) {
  throw new Error('usage: node run_installed_migrations.cjs <package> <from-exact> <to-exact>');
}

const workspace = process.cwd();
const workspaceRequire = createRequire(path.join(workspace, 'package.json'));
const packageJsonPath = workspaceRequire.resolve(`${packageName}/package.json`);
const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
const migrationReference = packageJson['ng-update'] && packageJson['ng-update'].migrations;
if (!migrationReference) {
  process.stdout.write(`MIGRATION_COLLECTION_EMPTY ${packageName}\n`);
  process.exit(0);
}

const collectionPath = migrationReference.startsWith('.')
  ? path.resolve(path.dirname(packageJsonPath), migrationReference)
  : workspaceRequire.resolve(migrationReference);
const collection = JSON.parse(fs.readFileSync(collectionPath, 'utf8'));
const semver = workspaceRequire('semver');
const migrations = Object.entries(collection.schematics || {})
  .filter(([, value]) => value && value.version)
  .map(([name, value]) => [name, value, semver.valid(value.version) || semver.coerce(value.version)])
  .filter(([, , version]) => version && semver.gt(version, fromVersion) && semver.lte(version, toVersion))
  .sort((left, right) => semver.compare(left[2], right[2]));

const { NodeWorkflow } = workspaceRequire('@angular-devkit/schematics/tools');
const workflow = new NodeWorkflow(workspace, {
  dryRun: false,
  force: false,
  resolvePaths: [workspace, path.dirname(collectionPath)],
});
workflow.reporter.subscribe((event) => process.stdout.write(`${event.kind} ${event.path}\n`));

function execute(schematic) {
  return new Promise((resolve, reject) => {
    workflow.execute({ collection: collectionPath, schematic, options: {} }).subscribe({
      error: reject,
      complete: resolve,
    });
  });
}

(async () => {
  process.stdout.write(`MIGRATION_COLLECTION ${packageName}\n`);
  for (const [name, metadata] of migrations) {
    process.stdout.write(`MIGRATION_BEGIN ${name} ${metadata.version}\n`);
    await execute(name);
    process.stdout.write(`MIGRATION_PASS ${name} ${metadata.version}\n`);
  }
  process.stdout.write(`MIGRATION_COMPLETE ${packageName} ${migrations.length}\n`);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
