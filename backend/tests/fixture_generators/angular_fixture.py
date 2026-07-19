"""Synthetic Angular fixtures are generated outside the platform repository."""
import json
from pathlib import Path


def create_angular_fixture(root: Path, name: str = "Customer Portal") -> Path:
    source = root / name
    (source / "src" / "app").mkdir(parents=True)
    (source / "package.json").write_text(json.dumps({"name": name, "dependencies": {"@angular/core": "18.2.0", "@angular/cli": "18.2.12"}}, indent=2), encoding="utf-8")
    (source / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3}), encoding="utf-8")
    (source / "angular.json").write_text(json.dumps({"version": 1, "projects": {"app": {"projectType": "application"}}}), encoding="utf-8")
    (source / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"target": "ES2022"}}), encoding="utf-8")
    return source


def create_angular_fixture_180x(root: Path, name: str = "Angular18Workspace") -> Path:
    """Create an Angular 18.0.x workspace fixture."""
    source = root / name
    (source / "src" / "app").mkdir(parents=True)
    (source / "package.json").write_text(
        json.dumps({
            "name": name,
            "dependencies": {
                "@angular/core": "18.0.0",
                "@angular/cli": "18.0.6",
                "rxjs": "7.8.1",
                "zone.js": "0.14.0",
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": {}}, indent=2),
        encoding="utf-8",
    )
    (source / "angular.json").write_text(
        json.dumps({
            "version": 1,
            "projects": {
                "app": {
                    "projectType": "application",
                    "root": "",
                    "sourceRoot": "src",
                    "architect": {
                        "build": {
                            "builder": "@angular-devkit/build-angular:browser",
                            "options": {"outputPath": "dist"},
                        },
                    },
                },
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "tsconfig.json").write_text(
        json.dumps({
            "compilerOptions": {
                "target": "ES2022",
                "module": "ES2022",
                "lib": ["ES2022", "dom"],
                "experimentalDecorators": True,
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "src" / "app" / "main.ts").write_text(
        "import { platformBrowserDynamic } from '@angular/platform-browser-dynamic';\n"
        "import { AppModule } from './app.module';\n"
        "platformBrowserDynamic().bootstrapModule(AppModule)\n"
        "  .catch(err => console.error(err));\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "app.module.ts").write_text(
        "import { NgModule } from '@angular/core';\n"
        "import { BrowserModule } from '@angular/platform-browser';\n"
        "import { AppComponent } from './app.component';\n"
        "@NgModule({\n"
        "  declarations: [AppComponent],\n"
        "  imports: [BrowserModule],\n"
        "  bootstrap: [AppComponent],\n"
        "})\n"
        "export class AppModule {}\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "app.component.ts").write_text(
        "import { Component } from '@angular/core';\n"
        "@Component({\n"
        "  selector: 'app-root',\n"
        "  template: '<h1>{{ title }}</h1>',\n"
        "})\n"
        "export class AppComponent {\n"
        "  title = 'angular-18-workspace';\n"
        "}\n",
        encoding="utf-8",
    )
    return source


def create_passable_fixture(root: Path, name: str = "PassableWorkspace") -> Path:
    """Create a workspace that should build cleanly (NG 18.2.x, basic app)."""
    source = root / name
    (source / "src" / "app").mkdir(parents=True)
    (source / "package.json").write_text(
        json.dumps({
            "name": name,
            "dependencies": {
                "@angular/core": "18.2.0",
                "@angular/cli": "18.2.12",
                "@angular/platform-browser": "18.2.0",
                "@angular/platform-browser-dynamic": "18.2.0",
                "@angular/compiler": "18.2.0",
                "@angular/compiler-cli": "18.2.0",
                "rxjs": "7.8.1",
                "zone.js": "0.14.0",
                "typescript": "5.4.5",
            },
            "devDependencies": {
                "@angular-devkit/build-angular": "18.2.12",
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": {}}, indent=2),
        encoding="utf-8",
    )
    (source / "angular.json").write_text(
        json.dumps({
            "version": 1,
            "projects": {
                "app": {
                    "projectType": "application",
                    "root": "",
                    "sourceRoot": "src",
                    "architect": {
                        "build": {
                            "builder": "@angular-devkit/build-angular:browser",
                            "options": {"outputPath": "dist"},
                        },
                    },
                },
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "tsconfig.json").write_text(
        json.dumps({
            "compilerOptions": {
                "target": "ES2022",
                "module": "ES2022",
                "moduleResolution": "bundler",
                "lib": ["ES2022", "dom"],
                "experimentalDecorators": True,
                "strict": True,
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "src" / "app" / "main.ts").write_text(
        "import { platformBrowserDynamic } from '@angular/platform-browser-dynamic';\n"
        "import { AppModule } from './app.module';\n"
        "platformBrowserDynamic().bootstrapModule(AppModule)\n"
        "  .catch(err => console.error(err));\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "app.module.ts").write_text(
        "import { NgModule } from '@angular/core';\n"
        "import { BrowserModule } from '@angular/platform-browser';\n"
        "import { AppComponent } from './app.component';\n"
        "@NgModule({\n"
        "  declarations: [AppComponent],\n"
        "  imports: [BrowserModule],\n"
        "  bootstrap: [AppComponent],\n"
        "})\n"
        "export class AppModule {}\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "app.component.ts").write_text(
        "import { Component } from '@angular/core';\n"
        "@Component({\n"
        "  selector: 'app-root',\n"
        "  template: '<h1>{{ title }}</h1>',\n"
        "})\n"
        "export class AppComponent {\n"
        "  title = 'passable-workspace';\n"
        "}\n",
        encoding="utf-8",
    )
    return source


def create_compiler_error_fixture(root: Path, name: str = "CompilerErrorWorkspace") -> Path:
    """Create a workspace with intentional TypeScript syntax error in src/app/main.ts."""
    source = root / name
    (source / "src" / "app").mkdir(parents=True)
    (source / "package.json").write_text(
        json.dumps({
            "name": name,
            "dependencies": {
                "@angular/core": "18.2.0",
                "@angular/cli": "18.2.12",
                "@angular/platform-browser": "18.2.0",
                "@angular/platform-browser-dynamic": "18.2.0",
                "@angular/compiler": "18.2.0",
                "@angular/compiler-cli": "18.2.0",
                "rxjs": "7.8.1",
                "zone.js": "0.14.0",
                "typescript": "5.4.5",
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": {}}, indent=2),
        encoding="utf-8",
    )
    (source / "angular.json").write_text(
        json.dumps({
            "version": 1,
            "projects": {
                "app": {
                    "projectType": "application",
                    "root": "",
                    "sourceRoot": "src",
                    "architect": {
                        "build": {
                            "builder": "@angular-devkit/build-angular:browser",
                            "options": {"outputPath": "dist"},
                        },
                    },
                },
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "tsconfig.json").write_text(
        json.dumps({
            "compilerOptions": {
                "target": "ES2022",
                "module": "ES2022",
                "moduleResolution": "bundler",
                "lib": ["ES2022", "dom"],
                "experimentalDecorators": True,
                "strict": True,
            },
        }, indent=2),
        encoding="utf-8",
    )
    # Intentional TypeScript syntax error — missing closing parenthesis
    (source / "src" / "app" / "main.ts").write_text(
        "import { platformBrowserDynamic } from '@angular/platform-browser-dynamic';\n"
        "import { AppModule } from './app.module';\n"
        "platformBrowserDynamic().bootstrapModule(AppModule  // <-- intentional syntax error, missing closing paren\n"
        "  .catch(err => console.error(err));\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "app.module.ts").write_text(
        "import { NgModule } from '@angular/core';\n"
        "import { BrowserModule } from '@angular/platform-browser';\n"
        "import { AppComponent } from './app.component';\n"
        "@NgModule({\n"
        "  declarations: [AppComponent],\n"
        "  imports: [BrowserModule],\n"
        "  bootstrap: [AppComponent],\n"
        "})\n"
        "export class AppModule {}\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "app.component.ts").write_text(
        "import { Component } from '@angular/core';\n"
        "@Component({\n"
        "  selector: 'app-root',\n"
        "  template: '<h1>{{ title }}</h1>',\n"
        "})\n"
        "export class AppComponent {\n"
        "  title = 'compiler-error';\n"
        "}\n",
        encoding="utf-8",
    )
    return source


def create_dependency_conflict_fixture(root: Path, name: str = "DepConflictWorkspace") -> Path:
    """Create a workspace with incompatible @angular/core and rxjs versions."""
    source = root / name
    (source / "src" / "app").mkdir(parents=True)
    # Incompatible: @angular/core 19.0.0 requires rxjs ^7.8.0 but we pin rxjs 6.6.7
    (source / "package.json").write_text(
        json.dumps({
            "name": name,
            "dependencies": {
                "@angular/core": "19.0.0",
                "@angular/cli": "19.0.0",
                "@angular/platform-browser": "19.0.0",
                "@angular/platform-browser-dynamic": "19.0.0",
                "@angular/compiler": "19.0.0",
                "@angular/compiler-cli": "19.0.0",
                "rxjs": "6.6.7",
                "zone.js": "0.14.0",
                "typescript": "5.5.0",
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": {}}, indent=2),
        encoding="utf-8",
    )
    (source / "angular.json").write_text(
        json.dumps({
            "version": 1,
            "projects": {
                "app": {
                    "projectType": "application",
                    "root": "",
                    "sourceRoot": "src",
                    "architect": {
                        "build": {
                            "builder": "@angular-devkit/build-angular:browser",
                            "options": {"outputPath": "dist"},
                        },
                    },
                },
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "tsconfig.json").write_text(
        json.dumps({
            "compilerOptions": {
                "target": "ES2022",
                "module": "ES2022",
                "moduleResolution": "bundler",
                "lib": ["ES2022", "dom"],
                "experimentalDecorators": True,
                "strict": True,
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "src" / "app" / "main.ts").write_text(
        "import { platformBrowserDynamic } from '@angular/platform-browser-dynamic';\n"
        "import { AppModule } from './app.module';\n"
        "platformBrowserDynamic().bootstrapModule(AppModule)\n"
        "  .catch(err => console.error(err));\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "app.module.ts").write_text(
        "import { NgModule } from '@angular/core';\n"
        "import { BrowserModule } from '@angular/platform-browser';\n"
        "import { AppComponent } from './app.component';\n"
        "@NgModule({\n"
        "  declarations: [AppComponent],\n"
        "  imports: [BrowserModule],\n"
        "  bootstrap: [AppComponent],\n"
        "})\n"
        "export class AppModule {}\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "app.component.ts").write_text(
        "import { Component } from '@angular/core';\n"
        "@Component({\n"
        "  selector: 'app-root',\n"
        "  template: '<h1>{{ title }}</h1>',\n"
        "})\n"
        "export class AppComponent {\n"
        "  title = 'dep-conflict';\n"
        "}\n",
        encoding="utf-8",
    )
    return source


def create_environment_blocker_fixture(root: Path, name: str = "EnvBlockerWorkspace") -> Path:
    """Create a workspace with a pre-check script that fails (non-zero exit)."""
    source = root / name
    (source / "src" / "app").mkdir(parents=True)
    (source / "scripts").mkdir(parents=True, exist_ok=True)
    (source / "package.json").write_text(
        json.dumps({
            "name": name,
            "dependencies": {
                "@angular/core": "18.2.0",
                "@angular/cli": "18.2.12",
                "rxjs": "7.8.1",
                "zone.js": "0.14.0",
            },
            "scripts": {
                "precheck": "node scripts/precheck.js",
                "build": "ng build",
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": {}}, indent=2),
        encoding="utf-8",
    )
    (source / "angular.json").write_text(
        json.dumps({
            "version": 1,
            "projects": {
                "app": {
                    "projectType": "application",
                    "root": "",
                    "sourceRoot": "src",
                    "architect": {
                        "build": {
                            "builder": "@angular-devkit/build-angular:browser",
                            "options": {"outputPath": "dist"},
                        },
                    },
                },
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "tsconfig.json").write_text(
        json.dumps({
            "compilerOptions": {
                "target": "ES2022",
                "module": "ES2022",
                "lib": ["ES2022", "dom"],
                "experimentalDecorators": True,
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "scripts" / "precheck.js").write_text(
        "#!/usr/bin/env node\n"
        "console.log('Running pre-check...');\n"
        "console.error('Pre-check failed: Node version requirement not met.');\n"
        "process.exit(1);\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "main.ts").write_text(
        "import { platformBrowserDynamic } from '@angular/platform-browser-dynamic';\n"
        "import { AppModule } from './app.module';\n"
        "platformBrowserDynamic().bootstrapModule(AppModule)\n"
        "  .catch(err => console.error(err));\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "app.module.ts").write_text(
        "import { NgModule } from '@angular/core';\n"
        "import { BrowserModule } from '@angular/platform-browser';\n"
        "import { AppComponent } from './app.component';\n"
        "@NgModule({\n"
        "  declarations: [AppComponent],\n"
        "  imports: [BrowserModule],\n"
        "  bootstrap: [AppComponent],\n"
        "})\n"
        "export class AppModule {}\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "app.component.ts").write_text(
        "import { Component } from '@angular/core';\n"
        "@Component({\n"
        "  selector: 'app-root',\n"
        "  template: '<h1>{{ title }}</h1>',\n"
        "})\n"
        "export class AppComponent {\n"
        "  title = 'env-blocker';\n"
        "}\n",
        encoding="utf-8",
    )
    return source


def create_cancellable_fixture(root: Path, name: str = "CancellableWorkspace") -> Path:
    """Create a workspace with a blocking operation (setTimeout loop in main.ts)."""
    source = root / name
    (source / "src" / "app").mkdir(parents=True)
    (source / "package.json").write_text(
        json.dumps({
            "name": name,
            "dependencies": {
                "@angular/core": "18.2.0",
                "@angular/cli": "18.2.12",
                "rxjs": "7.8.1",
                "zone.js": "0.14.0",
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": {}}, indent=2),
        encoding="utf-8",
    )
    (source / "angular.json").write_text(
        json.dumps({
            "version": 1,
            "projects": {
                "app": {
                    "projectType": "application",
                    "root": "",
                    "sourceRoot": "src",
                    "architect": {
                        "build": {
                            "builder": "@angular-devkit/build-angular:browser",
                            "options": {"outputPath": "dist"},
                        },
                    },
                },
            },
        }, indent=2),
        encoding="utf-8",
    )
    (source / "tsconfig.json").write_text(
        json.dumps({
            "compilerOptions": {
                "target": "ES2022",
                "module": "ES2022",
                "lib": ["ES2022", "dom"],
                "experimentalDecorators": True,
            },
        }, indent=2),
        encoding="utf-8",
    )
    # Infinite setTimeout loop — blocking operation
    (source / "src" / "app" / "main.ts").write_text(
        "function blockingLoop(): void {\n"
        "  setTimeout(() => {\n"
        "    console.log('still running...');\n"
        "    blockingLoop();\n"
        "  }, 1000);\n"
        "}\n"
        "blockingLoop();\n",
        encoding="utf-8",
    )
    (source / "src" / "app" / "app.component.ts").write_text(
        "import { Component } from '@angular/core';\n"
        "@Component({\n"
        "  selector: 'app-root',\n"
        "  template: '<h1>{{ title }}</h1>',\n"
        "})\n"
        "export class AppComponent {\n"
        "  title = 'cancellable';\n"
        "}\n",
        encoding="utf-8",
    )
    return source
