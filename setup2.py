import os
import json
import zipfile
import subprocess
import shutil
import re
import sys
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import threading
import asyncio
from packaging import version
import socket
HOME_DIR = os.path.expanduser("~")
permissions = [
    ("android.permission.INTERNET", "Akses Internet"),
    ("android.permission.CAMERA", "Akses Kamera"),
    ("android.permission.RECORD_AUDIO", "Rekam Audio/Mikrofon"),
    ("android.permission.ACCESS_FINE_LOCATION", "Lokasi Akurat (GPS)"),
    ("android.permission.ACCESS_COARSE_LOCATION", "Lokasi Perkiraan (Jaringan)"),
    ("android.permission.READ_EXTERNAL_STORAGE", "Baca Penyimpanan Eksternal (hingga Android 10)"),
    ("android.permission.WRITE_EXTERNAL_STORAGE", "Tulis Penyimpanan Eksternal (hingga Android 10)"),
    ("android.permission.MANAGE_EXTERNAL_STORAGE", "Kelola Semua Penyimpanan (Android 11+, memerlukan persetujuan Google Play)"),
    ("android.permission.READ_MEDIA_IMAGES", "Baca Gambar (Android 13+)"),
    ("android.permission.READ_MEDIA_VIDEO", "Baca Video (Android 13+)"),
    ("android.permission.READ_MEDIA_AUDIO", "Baca Audio (Android 13+)"),
    ("android.permission.POST_NOTIFICATIONS", "Tampilkan Notifikasi (Android 13+)"),
    ("android.permission.READ_CONTACTS", "Baca Kontak"),
    ("android.permission.WRITE_CONTACTS", "Tulis Kontak"),
    ("android.permission.READ_CALENDAR", "Baca Kalender"),
    ("android.permission.WRITE_CALENDAR", "Tulis Kalender"),
    ("android.permission.SEND_SMS", "Kirim SMS"),
    ("android.permission.READ_PHONE_STATE", "Baca Status Telepon"),
    ("android.permission.CALL_PHONE", "Panggil Telepon Langsung")
]
class Colors:
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
print_lock = threading.Lock()
CACHE_DIR = os.path.join(HOME_DIR, ".cache", "build_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def check_internet():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False

def get_latest_npm_version(package_name):
    if not check_internet():
        return 'latest'
    try:
        import requests
        url = f"https://registry.npmjs.org/{package_name}/latest"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()['version']
    except:
        pass
    return 'latest'

def get_latest_maven_version(group, artifact):
    if not check_internet():
        return None
    try:
        import requests
        url = f"https://search.maven.org/solrsearch/select?q=g:{group}+AND+a:{artifact}&rows=1&wt=json"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data['response']['docs']:
                return data['response']['docs'][0]['latestVersion']
    except:
        pass
    return None

def get_library_versions():
    versions = {
        'capacitor': 'latest',
        'target_sdk': 34,
        'multidex': '2.0.1',
        'java': 'modern',
        'gradle_parallel': True
    }
    try:
        result = subprocess.run("npm show @capacitor/core version", shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            versions['capacitor'] = result.stdout.strip()
    except:
        pass
    try:
        sdk_path = None
        if os.path.exists("local.properties"):
            with open("local.properties") as f:
                for line in f:
                    if line.startswith("sdk.dir"):
                        sdk_path = line.split("=")[1].strip()
                        break
        if sdk_path:
            platforms_dir = os.path.join(sdk_path, "platforms")
            if os.path.exists(platforms_dir):
                android_versions = []
                for item in os.listdir(platforms_dir):
                    if item.startswith("android-"):
                        ver = item.replace("android-", "")
                        android_versions.append(int(ver))
                if android_versions:
                    versions['target_sdk'] = max(android_versions)
    except:
        pass
    multidex_ver = get_latest_maven_version("androidx.multidex", "multidex")
    if multidex_ver:
        versions['multidex'] = multidex_ver
    try:
        result = subprocess.run("java -version", shell=True, stderr=subprocess.PIPE, text=True, timeout=10)
        java_output = result.stderr.lower()
        if '1.8' in java_output:
            versions['java'] = '8'
        elif '11' in java_output:
            versions['java'] = '11'
        elif '17' in java_output:
            versions['java'] = '17'
        elif '21' in java_output:
            versions['java'] = '21'
    except:
        pass
    return versions

async def run_async(cmd, cwd=None, silent=True):
    if silent:
        process = await asyncio.create_subprocess_shell(
            cmd, cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    else:
        process = await asyncio.create_subprocess_shell(
            cmd, cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    await process.wait()
    return process.returncode

async def run_async_with_output(cmd, cwd=None):
    process = await asyncio.create_subprocess_shell(
        cmd, cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        print(line.decode().strip())
    await process.wait()
    return process.returncode

def print_success(msg):
    with print_lock:
        print(f"{Colors.GREEN}[✓] {msg}{Colors.END}")

def print_error(msg):
    with print_lock:
        print(f"{Colors.RED}[✗] {msg}{Colors.END}")

def print_warning(msg):
    with print_lock:
        print(f"{Colors.YELLOW}[!] {msg}{Colors.END}")

def add_permissions_to_manifest(abs_manifest_path, selected_perm):
    with open(abs_manifest_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r"\s*<!--\s*Permissions?\s*-->[\s\S]*?</manifest>\s*$", "\n</manifest>", content, flags=re.IGNORECASE)
    if ("android.permission.MANAGE_EXTERNAL_STORAGE" in selected_perm and ("android.permission.READ_EXTERNAL_STORAGE" in selected_perm or "android.permission.WRITE_EXTERNAL_STORAGE" in selected_perm)):
        print_warning("MANAGE_EXTERNAL_STORAGE sudah mencakup READ/WRITE_EXTERNAL_STORAGE")
    media_permissions = ["android.permission.READ_MEDIA_IMAGES", "android.permission.READ_MEDIA_VIDEO", "android.permission.READ_MEDIA_AUDIO"]
    has_media_permissions = any(perm in selected_perm for perm in media_permissions)
    permission_tags = []
    added_permissions = set()
    for perm in selected_perm:
        if perm in added_permissions:
            continue
        if perm == "android.permission.READ_EXTERNAL_STORAGE":
            permission_tags.append('<uses-permission android:maxSdkVersion="32" android:name="android.permission.READ_EXTERNAL_STORAGE"/>')
            added_permissions.add(perm)
        elif perm == "android.permission.WRITE_EXTERNAL_STORAGE":
            permission_tags.append('<uses-permission android:maxSdkVersion="29" android:name="android.permission.WRITE_EXTERNAL_STORAGE"/>')
            added_permissions.add(perm)
        elif perm == "android.permission.MANAGE_EXTERNAL_STORAGE":
            permission_tags.append('<uses-permission android:name="android.permission.MANAGE_EXTERNAL_STORAGE" />')
            added_permissions.add(perm)
        elif perm == "android.permission.POST_NOTIFICATIONS":
            permission_tags.append('<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />')
            added_permissions.add(perm)
        elif perm in media_permissions:
            permission_tags.append(f'<uses-permission android:name="{perm}" />')
            added_permissions.add(perm)
        else:
            permission_tags.append(f'<uses-permission android:name="{perm}" />')
            added_permissions.add(perm)
    if has_media_permissions:
        permission_tags.append('<uses-permission android:name="android.permission.READ_MEDIA_VISUAL_USER_SELECTED" />')
    permissions_str = "\n    ".join(permission_tags)
    application_start = content.find("<application")
    if application_start != -1:
        content = content[:application_start] + permissions_str + "\n    " + content[application_start:]
    if ("android.permission.READ_EXTERNAL_STORAGE" in selected_perm or "android.permission.WRITE_EXTERNAL_STORAGE" in selected_perm):
        if 'android:requestLegacyExternalStorage="true"' not in content:
            content = content.replace("<application", '<application android:requestLegacyExternalStorage="true"')
    with open(abs_manifest_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content

def modify_manifest_attributes(manifest_path, app_id, fullscreen_mode, screen_orientation, version_name, version_code):
    with open(manifest_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r'android:versionCode="\d+"', f'android:versionCode="{version_code}"', content)
    content = re.sub(r'android:versionName="[^"]+"', f'android:versionName="{version_name}"', content)
    pattern = r'(<activity\s+[^>]*android:name\s*=\s*["\'](?:{}[\.\w]*|MainActivity)["\'][^>]*)>'.format(re.escape(app_id))
    match = re.search(pattern, content)
    if not match:
        pattern = r'(<activity\s+[^>]*android:name\s*=\s*["\'][\.\w]+["\'][^>]*)>'
        match = re.search(pattern, content)
        if not match:
            return
    activity_tag = match.group(1)
    new_tag = activity_tag
    if fullscreen_mode in ["1", "2"]:
        if "android:theme" not in new_tag:
            new_tag += ' android:theme="@style/Theme.AppCompat.NoActionBar"'
    if screen_orientation == "1":
        new_tag = re.sub(r'android:screenOrientation\s*=\s*["\'][^"\']*["\']', '', new_tag)
        new_tag += ' android:screenOrientation="portrait"'
    elif screen_orientation == "2":
        new_tag = re.sub(r'android:screenOrientation\s*=\s*["\'][^"\']*["\']', '', new_tag)
        new_tag += ' android:screenOrientation="landscape"'
    if "android:configChanges" not in new_tag:
        new_tag += ' android:configChanges="keyboard|keyboardHidden|orientation|screenSize"'
    content = content.replace(activity_tag, new_tag)
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(content)

def create_proguard_rules(project_dir):
    proguard_path = os.path.join(project_dir, "android", "app", "proguard-rules.pro")
    rules = '''-optimizationpasses 5
-allowaccessmodification
-overloadaggressively
-repackageclasses ''
-dontusemixedcaseclassnames
-dontskipnonpubliclibraryclasses
-verbose
-keep class com.getcapacitor.** { *; }
-keep class com.google.android.gms.** { *; }
-keep class * extends com.getcapacitor.Plugin
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-assumenosideeffects class android.util.Log {
    public static boolean isLoggable(java.lang.String, int);
    public static int v(...);
    public static int d(...);
    public static int i(...);
    public static int w(...);
    public static int e(...);
}
-keep class androidx.multidex.** { *; }'''
    try:
        with open(proguard_path, 'w') as f:
            f.write(rules)
        return True
    except Exception:
        return False

def ensure_multidex_in_manifest(manifest_path):
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if 'android:name="androidx.multidex.MultiDexApplication"' not in content:
            content = re.sub(r'(<application\s+)', r'\1android:name="androidx.multidex.MultiDexApplication" ', content)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception:
        pass

def modify_build_gradle_auto(build_gradle_path, version_code, version_name):
    try:
        with open(build_gradle_path, 'r') as f:
            content = f.read()
        versions = get_library_versions()
        content = re.sub(r'versionCode\s+\d+', f'versionCode {version_code}', content)
        content = re.sub(r'versionName\s+".*?"', f'versionName "{version_name}"', content)
        content = re.sub(r'minSdkVersion\s+\d+', 'minSdkVersion 21', content)
        target_sdk = versions.get('target_sdk', 34)
        content = re.sub(r'targetSdkVersion\s+\d+', f'targetSdkVersion {target_sdk}', content)
        if 'multiDexEnabled' not in content:
            default_config_pattern = r'(defaultConfig\s*\{[^}]+)'
            multidex_config = '\n        multiDexEnabled true'
            content = re.sub(default_config_pattern, r'\1' + multidex_config, content, flags=re.DOTALL)
        if 'buildTypes' in content:
            build_types_config = '''
    buildTypes {
        release {
            minifyEnabled true
            shrinkResources true
            crunchPngs true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
        debug {
            minifyEnabled true
            shrinkResources true
            crunchPngs true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }
    }
'''
            content = re.sub(r'buildTypes\s*\{[^}]+\}[^}]*\}', build_types_config, content, flags=re.DOTALL)
        multidex_ver = versions.get('multidex', '2.0.1')
        multidex_dep = f'\n    implementation "androidx.multidex:multidex:{multidex_ver}"'
        if 'implementation "androidx.multidex:multidex' not in content:
            dependencies_pattern = r'(dependencies\s*\{)'
            content = re.sub(dependencies_pattern, r'\1' + multidex_dep, content)
        else:
            content = re.sub(
                r'implementation "androidx\.multidex:multidex:[^"]*"',
                f'implementation "androidx.multidex:multidex:{multidex_ver}"',
                content
            )
        with open(build_gradle_path, 'w') as f:
            f.write(content)
        print_success(f"Build.gradle diupdate: targetSdk={target_sdk}, multidex={multidex_ver}")
    except Exception as e:
        print_error(f"Gagal modify build.gradle: {e}")

def get_image_size(image_path):
    with Image.open(image_path) as img:
        return img.size

def resize_and_convert_to_webp(original_image_path, source_image_path):
    try:
        target_size = get_image_size(original_image_path)
        with Image.open(source_image_path) as src_img:
            src_img = src_img.convert("RGBA")
            resized_img = src_img.resize(target_size, Image.LANCZOS)
            webp_path = os.path.splitext(original_image_path)[0] + ".webp"
            resized_img.save(webp_path, "WEBP", quality=80, method=6)
        if not original_image_path.lower().endswith(".webp"):
            try:
                os.remove(original_image_path)
            except Exception:
                pass
        return True
    except Exception:
        return False

def scan_and_replace_with_webp(res_folder_path, source_image_path):
    if not os.path.exists(res_folder_path):
        return
    if not os.path.exists(source_image_path):
        return
    image_files = []
    for root, dirs, files in os.walk(res_folder_path):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                image_files.append(os.path.join(root, file))
    success_count = 0
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = {executor.submit(resize_and_convert_to_webp, img_path, source_image_path): img_path for img_path in image_files}
        for future in as_completed(futures):
            if future.result():
                success_count += 1
    if success_count > 0:
        print_success(f"Berhasil mengganti {success_count} gambar!")

def replace_images(project_dir, image_path=None):
    if not image_path:
        return
    res_path = os.path.join(project_dir, "android", "app", "src", "main", "res")
    scan_and_replace_with_webp(res_path, image_path)

def copy_to_temp_dir(project_dir, temp_dir):
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            sys.exit(1)
    os.makedirs(temp_dir, exist_ok=True)
    for item in os.listdir(project_dir):
        if item == 'node_modules':
            continue
        src_path = os.path.join(project_dir, item)
        dst_path = os.path.join(temp_dir, item)
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path, ignore=shutil.ignore_patterns('node_modules'))
        else:
            shutil.copy2(src_path, dst_path)
    return temp_dir

async def install_filesystem_plugin_async(working_dir):
    os.chdir(working_dir)
    if not os.path.exists("package.json"):
        print_error("package.json tidak ditemukan!")
        return False
    await run_async("npm install @capacitor/filesystem@latest", silent=True)
    print_success("Plugin filesystem berhasil diinstal!")
    return True

async def parallel_npm_install_async(packages, cwd=None):
    tasks = []
    for pkg in packages:
        tasks.append(run_async(f"npm install {pkg}", cwd=cwd, silent=True))
    results = await asyncio.gather(*tasks)
    return all(r == 0 for r in results)

def enable_gradle_parallel_auto(android_dir):
    gradle_props = os.path.join(android_dir, "gradle.properties")
    versions = get_library_versions()
    with open(gradle_props, 'a') as f:
        f.write("\n# Auto-generated parallel config\n")
        f.write("org.gradle.parallel=true\n")
        f.write("org.gradle.caching=true\n")
        f.write("org.gradle.daemon=true\n")
        if versions.get('java') in ['8', '11', '17', '21']:
            f.write("org.gradle.jvmargs=-Xmx4096m -XX:MaxMetaspaceSize=512m -XX:+HeapDumpOnOutOfMemoryError\n")
            print_success(f"Java {versions.get('java')} detected: using MaxMetaspaceSize")
        else:
            f.write("org.gradle.jvmargs=-Xmx4096m -XX:+HeapDumpOnOutOfMemoryError\n")
            print_success("Using safe JVM args")

async def build_android_async(working_dir, build_type):
    root_dir = os.getcwd()
    with print_lock:
        print(f"\n{Colors.CYAN}Memulai proses build Android...{Colors.END}")
    android_dir = os.path.join(working_dir, "android")
    if not os.path.exists(android_dir):
        print_error("Direktori android tidak ditemukan!")
        return False
    enable_gradle_parallel_auto(android_dir)
    os.chdir(android_dir)
    await run_async("chmod +x gradlew", silent=True)
    if build_type == "1":
        with print_lock:
            print(f"{Colors.YELLOW}Menjalankan ./gradlew assembleDebug (parallel mode)...{Colors.END}")
        result = await run_async_with_output("./gradlew assembleDebug", cwd=android_dir)
        if result == 0:
            apk_path = os.path.join(android_dir, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
            if os.path.exists(apk_path):
                print_success(f"Build debug berhasil! APK tersedia di: {apk_path}")
                shutil.copy2(apk_path, os.path.join(root_dir, "app-debug.apk"))
                with print_lock:
                    print(f"APK dicopy ke: {os.path.join(root_dir, 'app-debug.apk')}")
            else:
                print_success("Build debug berhasil!")
            return True
        else:
            print_error("Build debug gagal!")
            return False
    elif build_type == "2":
        with print_lock:
            print(f"{Colors.YELLOW}Menjalankan ./gradlew assembleRelease (parallel mode)...{Colors.END}")
        result = await run_async_with_output("./gradlew assembleRelease", cwd=android_dir)
        if result == 0:
            apk_path = os.path.join(android_dir, "app", "build", "outputs", "apk", "release", "app-release.apk")
            if os.path.exists(apk_path):
                print_success(f"Build release berhasil! APK tersedia di: {apk_path}")
                shutil.copy2(apk_path, os.path.join(root_dir, "app-release.apk"))
                with print_lock:
                    print(f"APK dicopy ke: {os.path.join(root_dir, 'app-release.apk')}")
            else:
                print_success("Build release berhasil!")
            return True
        else:
            print_error("Build release gagal!")
            return False
    else:
        print_error("Tipe build tidak dikenal!")
        return False

async def build_both_async(working_dir):
    root_dir = os.getcwd()
    with print_lock:
        print(f"\n{Colors.CYAN}Memulai proses build Android (Debug + Release parallel)...{Colors.END}")
    android_dir = os.path.join(working_dir, "android")
    if not os.path.exists(android_dir):
        print_error("Direktori android tidak ditemukan!")
        return False
    enable_gradle_parallel_auto(android_dir)
    os.chdir(android_dir)
    await run_async("chmod +x gradlew", silent=True)
    with print_lock:
        print(f"{Colors.YELLOW}Menjalankan ./gradlew assembleDebug assembleRelease --parallel...{Colors.END}")
    result = await run_async_with_output("./gradlew assembleDebug assembleRelease --parallel", cwd=android_dir)
    if result == 0:
        debug_apk = os.path.join(android_dir, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
        release_apk = os.path.join(android_dir, "app", "build", "outputs", "apk", "release", "app-release.apk")
        if os.path.exists(debug_apk):
            shutil.copy2(debug_apk, os.path.join(root_dir, "app-debug.apk"))
            print_success("APK Debug dicopy")
        if os.path.exists(release_apk):
            shutil.copy2(release_apk, os.path.join(root_dir, "app-release.apk"))
            print_success("APK Release dicopy")
        return True
    else:
        print_error("Build gagal!")
        return False

def find_icon_file(working_dir):
    icon_path = os.path.join(working_dir, "icon.png")
    if os.path.exists(icon_path):
        return icon_path
    www_icon = os.path.join(working_dir, "www", "icon.png")
    if os.path.exists(www_icon):
        return www_icon
    build_icon = os.path.join(working_dir, "build", "icon.png")
    if os.path.exists(build_icon):
        return build_icon
    dist_icon = os.path.join(working_dir, "dist", "icon.png")
    if os.path.exists(dist_icon):
        return dist_icon
    for root, dirs, files in os.walk(working_dir):
        if 'icon.png' in files:
            return os.path.join(root, 'icon.png')
    return None

def parallel_setup_html_tasks(working_dir, app_name, app_id, selected_perm, fullscreen_mode, screen_orientation, version_name, version_code, image_path):
    abs_dir = os.path.abspath(working_dir)
    manifest_path = os.path.join(abs_dir, "android", "app", "src", "main", "AndroidManifest.xml")
    build_gradle_path = os.path.join(abs_dir, "android", "app", "build.gradle")
    futures = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        if os.path.exists(build_gradle_path):
            futures.append(executor.submit(modify_build_gradle_auto, build_gradle_path, version_code, version_name))
            futures.append(executor.submit(create_proguard_rules, abs_dir))
        manifest_result = None
        if selected_perm:
            manifest_future = executor.submit(add_permissions_to_manifest, manifest_path, selected_perm)
            manifest_result = manifest_future.result()
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print_error(f"Error dalam parallel task: {e}")
    if manifest_result:
        ensure_multidex_in_manifest(manifest_path)
    modify_manifest_attributes(manifest_path, app_id, fullscreen_mode, screen_orientation, version_name, version_code)
    package_path = app_id.replace('.', '/')
    main_activity_path = os.path.join(abs_dir, "android", "app", "src", "main", "java", package_path, "MainActivity.java")
    if os.path.exists(main_activity_path):
        with open(main_activity_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "setRequestedOrientation" not in content and screen_orientation != "0":
            orientation_code = ""
            if screen_orientation == "1":
                orientation_code = "setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);"
            elif screen_orientation == "2":
                orientation_code = "setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);"
            if orientation_code:
                content = content.replace("super.onCreate(savedInstanceState);", f"super.onCreate(savedInstanceState);\n        {orientation_code}")
        if fullscreen_mode in ["1", "2"] and "SYSTEM_UI_FLAG_FULLSCREEN" not in content:
            fullscreen_code = """
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN, WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_FULLSCREEN |
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        );"""
            content = content.replace("super.onCreate(savedInstanceState);", f"super.onCreate(savedInstanceState);{fullscreen_code}")
        with open(main_activity_path, "w", encoding="utf-8") as f:
            f.write(content)
    if image_path and os.path.exists(image_path):
        replace_images(abs_dir, image_path)

def parallel_setup_react_tasks(working_dir, app_name, app_id, selected_perm, fullscreen_mode, screen_orientation, version_name, version_code, image_path):
    abs_dir = os.path.abspath(working_dir)
    manifest_path = os.path.join(abs_dir, "android", "app", "src", "main", "AndroidManifest.xml")
    build_gradle_path = os.path.join(abs_dir, "android", "app", "build.gradle")
    futures = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        if os.path.exists(build_gradle_path):
            futures.append(executor.submit(modify_build_gradle_auto, build_gradle_path, version_code, version_name))
            futures.append(executor.submit(create_proguard_rules, abs_dir))
        manifest_result = None
        if selected_perm:
            manifest_future = executor.submit(add_permissions_to_manifest, manifest_path, selected_perm)
            manifest_result = manifest_future.result()
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print_error(f"Error dalam parallel task: {e}")
    if manifest_result:
        ensure_multidex_in_manifest(manifest_path)
    modify_manifest_attributes(manifest_path, app_id, fullscreen_mode, screen_orientation, version_name, version_code)
    package_path = app_id.replace('.', '/')
    main_activity_path = os.path.join(abs_dir, "android", "app", "src", "main", "java", package_path, "MainActivity.java")
    if os.path.exists(main_activity_path):
        with open(main_activity_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "setRequestedOrientation" not in content and screen_orientation != "0":
            orientation_code = ""
            if screen_orientation == "1":
                orientation_code = "setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);"
            elif screen_orientation == "2":
                orientation_code = "setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);"
            if orientation_code:
                content = content.replace("super.onCreate(savedInstanceState);", f"super.onCreate(savedInstanceState);\n        {orientation_code}")
        if fullscreen_mode in ["1", "2"] and "SYSTEM_UI_FLAG_FULLSCREEN" not in content:
            fullscreen_code = """
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN, WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_FULLSCREEN |
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        );"""
            content = content.replace("super.onCreate(savedInstanceState);", f"super.onCreate(savedInstanceState);{fullscreen_code}")
        with open(main_activity_path, "w", encoding="utf-8") as f:
            f.write(content)
    if image_path and os.path.exists(image_path):
        replace_images(abs_dir, image_path)

async def setup_html_project_async(working_dir, app_name, app_id, version_name, version_code, selected_perm, fullscreen_mode, screen_orientation, build_type, image_path):
    abs_dir = os.path.abspath(working_dir)
    if not os.path.exists("www"):
        os.makedirs("www", exist_ok=True)
    items_to_move = []
    for item in os.listdir("."):
        if item not in ["www", "node_modules", "icon.png", "config.json", os.path.basename(__file__)]:
            items_to_move.append(item)
    def move_files():
        for item in items_to_move:
            src_path = os.path.join(".", item)
            dst_path = os.path.join("www", item)
            if os.path.isfile(src_path):
                try:
                    shutil.move(src_path, dst_path)
                except:
                    pass
            elif os.path.isdir(src_path):
                try:
                    shutil.move(src_path, dst_path)
                except:
                    pass
    async def run_npm_init_async():
        await run_async("npm init -y", silent=True)
    async def run_npm_install_parallel():
        packages = ["@capacitor/core", "@capacitor/cli", "@capacitor/android", "@capacitor/app"]
        await parallel_npm_install_async(packages)
    with ThreadPoolExecutor(max_workers=2) as executor:
        move_future = executor.submit(move_files)
        move_future.result()
    await asyncio.gather(
        run_npm_init_async(),
        run_npm_install_parallel()
    )
    await run_async(f'npx cap init "{app_name}" "{app_id}" --web-dir www', silent=True)
    await run_async("npx cap add android", silent=True)
    await run_async("npx cap copy android", silent=True)
    storage_permissions = ["android.permission.READ_EXTERNAL_STORAGE", "android.permission.WRITE_EXTERNAL_STORAGE", "android.permission.MANAGE_EXTERNAL_STORAGE"]
    plugin_task = None
    if any(perm in selected_perm for perm in storage_permissions):
        plugin_task = asyncio.create_task(install_filesystem_plugin_async(working_dir))
    sync_task = asyncio.create_task(run_async("npx cap sync android", silent=True))
    if plugin_task:
        await plugin_task
    await sync_task
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, parallel_setup_html_tasks, working_dir, app_name, app_id, selected_perm, fullscreen_mode, screen_orientation, version_name, version_code, image_path)
    with print_lock:
        print(f"\n{Colors.GREEN}[✓] Proses Setup Selesai!{Colors.END}")
        print(f"{Colors.CYAN}Informasi Aplikasi:{Colors.END}")
        print(f"Nama: {app_name}")
        print(f"App ID: {app_id}")
        print(f"Versi: {version_name} (code: {version_code})")
        print(f"Tipe Build: {'Debug' if build_type == '1' else 'Release' if build_type == '2' else 'Debug+Release'}")
    if build_type == "3":
        await build_both_async(abs_dir)
    else:
        await build_android_async(abs_dir, build_type)

async def setup_react_project_async(working_dir, app_name, app_id, version_name, version_code, selected_perm, fullscreen_mode, screen_orientation, build_type, image_path):
    abs_dir = os.path.abspath(working_dir)
    async def run_npm_install_parallel():
        packages = ["@capacitor/core", "@capacitor/cli", "@capacitor/android", "@capacitor/app"]
        await parallel_npm_install_async(packages)
    async def run_npm_build_async():
        await run_async("npm run build", silent=False)
    await asyncio.gather(
        run_npm_install_parallel(),
        run_npm_build_async()
    )
    await run_async(f'npx cap init "{app_name}" "{app_id}" --web-dir build', silent=True)
    await run_async("npx cap add android", silent=True)
    await run_async("npx cap copy android", silent=True)
    storage_permissions = ["android.permission.READ_EXTERNAL_STORAGE", "android.permission.WRITE_EXTERNAL_STORAGE", "android.permission.MANAGE_EXTERNAL_STORAGE"]
    plugin_task = None
    if any(perm in selected_perm for perm in storage_permissions):
        plugin_task = asyncio.create_task(install_filesystem_plugin_async(working_dir))
    sync_task = asyncio.create_task(run_async("npx cap sync android", silent=True))
    if plugin_task:
        await plugin_task
    await sync_task
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, parallel_setup_react_tasks, working_dir, app_name, app_id, selected_perm, fullscreen_mode, screen_orientation, version_name, version_code, image_path)
    with print_lock:
        print(f"\n{Colors.GREEN}[✓] Proses Setup Selesai!{Colors.END}")
        print(f"{Colors.CYAN}Informasi Aplikasi:{Colors.END}")
        print(f"Nama: {app_name}")
        print(f"App ID: {app_id}")
        print(f"Versi: {version_name} (code: {version_code})")
        print(f"Tipe Build: {'Debug' if build_type == '1' else 'Release' if build_type == '2' else 'Debug+Release'}")
    if build_type == "3":
        await build_both_async(abs_dir)
    else:
        await build_android_async(abs_dir, build_type)

def extract_and_setup(zip_path):
    temp_dir = os.path.join(HOME_DIR, ".cache", "build_temp")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        zipf.extractall(temp_dir)
    current_dir = os.getcwd()
    config_path = os.path.join(current_dir, "config.json")
    icon_path = os.path.join(current_dir, "icon.png")
    if not os.path.exists(config_path):
        print_error("config.json tidak ditemukan di root repository!")
        return
    with open(config_path, 'r') as f:
        config = json.load(f)
    project_type = config.get("project_type")
    app_name = config.get("app_name")
    app_id = config.get("app_id")
    version_name = config.get("version_name")
    version_code = config.get("version_code")
    selected_perm = config.get("selected_permissions", [])
    fullscreen_mode = config.get("fullscreen_mode", "0")
    screen_orientation = config.get("screen_orientation", "0")
    build_type = config.get("build_type", "1")
    if os.path.exists(icon_path):
        shutil.copy2(icon_path, temp_dir)
    os.chdir(temp_dir)
    if project_type == 1:
        asyncio.run(setup_html_project_async(temp_dir, app_name, app_id, version_name, version_code, selected_perm, fullscreen_mode, screen_orientation, build_type, icon_path if os.path.exists(icon_path) else None))
    elif project_type == 2:
        asyncio.run(setup_react_project_async(temp_dir, app_name, app_id, version_name, version_code, selected_perm, fullscreen_mode, screen_orientation, build_type, icon_path if os.path.exists(icon_path) else None))
    else:
        print_error("Jenis proyek tidak dikenal!")

def tool2_builder():
    current_dir = os.getcwd()
    zip_path = os.path.join(current_dir, "game.capzip")
    if not os.path.exists(zip_path):
        print_error(f"File game.capzip tidak ditemukan di direktori: {current_dir}")
        print_error("Pastikan file game.capzip berada di direktori yang sama dengan tools ini dijalankan.")
        sys.exit(1)
    extract_and_setup(zip_path)

if __name__ == "__main__":
    tool2_builder()
