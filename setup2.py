import os
import json
import zipfile
import subprocess
import shutil
import re
import sys
from PIL import Image
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
def print_success(msg):
    print(f"{Colors.GREEN}[✓] {msg}{Colors.END}")
def print_error(msg):
    print(f"{Colors.RED}[✗] {msg}{Colors.END}")
def print_warning(msg):
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
def modify_build_gradle(build_gradle_path, version_code, version_name):
    try:
        with open(build_gradle_path, 'r') as f:
            content = f.read()
        content = re.sub(r'versionCode\s+\d+', f'versionCode {version_code}', content)
        content = re.sub(r'versionName\s+".*?"', f'versionName "{version_name}"', content)
        content = re.sub(r'minSdkVersion\s+\d+', 'minSdkVersion 23', content)
        content = re.sub(r'targetSdkVersion\s+\d+', 'targetSdkVersion 34', content)
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
        if 'implementation "androidx.multidex:multidex' not in content:
            dependencies_pattern = r'(dependencies\s*\{)'
            multidex_dep = '\n    implementation "androidx.multidex:multidex:2.0.1"'
            content = re.sub(dependencies_pattern, r'\1' + multidex_dep, content)
        with open(build_gradle_path, 'w') as f:
            f.write(content)
    except Exception:
        pass
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
    success_count = 0
    for root, dirs, files in os.walk(res_folder_path):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                full_path = os.path.join(root, file)
                try:
                    if resize_and_convert_to_webp(full_path, source_image_path):
                        success_count += 1
                except Exception:
                    pass
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
def install_filesystem_plugin(working_dir):
    os.chdir(working_dir)
    if not os.path.exists("package.json"):
        print_error("package.json tidak ditemukan!")
        return False
    result = subprocess.run("npm list @capacitor/core", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode != 0:
        subprocess.run("npm install @capacitor/core", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = subprocess.run("npm install @capacitor/filesystem", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode == 0:
        print_success("Plugin berhasil diinstal!")
        subprocess.run("npx cap sync android", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    else:
        print_error("Gagal menginstal plugin Filesystem!")
        print_warning("Mencoba alternatif: menginstal versi stabil...")
        result = subprocess.run("npm install @capacitor/filesystem@latest", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            print_success("Plugin berhasil diinstal")
            subprocess.run("npx cap sync android", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        else:
            print_error("Tetap gagal menginstal plugin Filesystem")
            return False
def build_android(working_dir, build_type):
    root_dir = os.getcwd()
    print(f"\n{Colors.CYAN}Memulai proses build Android...{Colors.END}")
    android_dir = os.path.join(working_dir, "android")
    if not os.path.exists(android_dir):
        print_error("Direktori android tidak ditemukan!")
        return False
    os.chdir(android_dir)
    subprocess.run("chmod +x gradlew", shell=True)
    if build_type == "1":
        print(f"{Colors.YELLOW}Menjalankan ./gradlew assembleDebug...{Colors.END}")
        process = subprocess.Popen("./gradlew assembleDebug --parallel --configuration-cache", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(line, end='')
        process.wait()
        result = process.returncode
        if result == 0:
            apk_path = os.path.join(android_dir, "app", "build", "outputs", "apk", "debug", "app-debug.apk")
            if os.path.exists(apk_path):
                print_success(f"Build debug berhasil! APK tersedia di: {apk_path}")
                shutil.copy2(apk_path, os.path.join(root_dir, "app-debug.apk"))
                print(f"APK dicopy ke: {os.path.join(root_dir, 'app-debug.apk')}")
            else:
                print_success("Build debug berhasil!")
            return True
        else:
            print_error("Build debug gagal!")
            return False
    elif build_type == "2":
        print(f"{Colors.YELLOW}Menjalankan ./gradlew assembleRelease...{Colors.END}")
        process = subprocess.Popen("./gradlew assembleRelease --parallel --configuration-cache", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(line, end='')
        process.wait()
        result = process.returncode
        if result == 0:
            apk_path = os.path.join(android_dir, "app", "build", "outputs", "apk", "release", "app-release.apk")
            if os.path.exists(apk_path):
                print_success(f"Build release berhasil! APK tersedia di: {apk_path}")
                shutil.copy2(apk_path, os.path.join(root_dir, "app-release.apk"))
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
def setup_html_project(working_dir, app_name, app_id, version_name, version_code, selected_perm, fullscreen_mode, screen_orientation, build_type, image_path):
    abs_dir = os.path.abspath(working_dir)
    manifest_path = os.path.join(abs_dir, "android", "app", "src", "main", "AndroidManifest.xml")
    if not os.path.exists("www"):
        os.makedirs("www", exist_ok=True)
    items_to_move = []
    for item in os.listdir("."):
        if item not in ["www", "node_modules", "icon.png", "config.json", os.path.basename(__file__)]:
            items_to_move.append(item)
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
    subprocess.run("npm init -y", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("npm install @capacitor/core @capacitor/cli @capacitor/android @capacitor/app", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(f'npx cap init "{app_name}" "{app_id}" --web-dir www', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("npx cap add android", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("npx cap copy android", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("npx cap sync android", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    storage_permissions = ["android.permission.READ_EXTERNAL_STORAGE", "android.permission.WRITE_EXTERNAL_STORAGE", "android.permission.MANAGE_EXTERNAL_STORAGE"]
    if any(perm in selected_perm for perm in storage_permissions):
        install_filesystem_plugin(working_dir)
    build_gradle_path = os.path.join(abs_dir, "android", "app", "build.gradle")
    if os.path.exists(build_gradle_path):
        modify_build_gradle(build_gradle_path, version_code, version_name)
        create_proguard_rules(abs_dir)
        ensure_multidex_in_manifest(manifest_path)
    if selected_perm:
        add_permissions_to_manifest(manifest_path, selected_perm)
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
    print(f"\n{Colors.GREEN}[✓] Proses Setup Selesai!{Colors.END}")
    print(f"{Colors.CYAN}Informasi Aplikasi:{Colors.END}")
    print(f"Nama: {app_name}")
    print(f"App ID: {app_id}")
    print(f"Versi: {version_name} (code: {version_code})")
    print(f"Tipe Build: {'Debug' if build_type == '1' else 'Release'}")
    build_android(abs_dir, build_type)
def setup_react_project(working_dir, app_name, app_id, version_name, version_code, selected_perm, fullscreen_mode, screen_orientation, build_type, image_path):
    abs_dir = os.path.abspath(working_dir)
    manifest_path = os.path.join(abs_dir, "android", "app", "src", "main", "AndroidManifest.xml")
    subprocess.run("npm install @capacitor/core @capacitor/cli @capacitor/android @capacitor/app", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(f'npx cap init "{app_name}" "{app_id}" --web-dir build', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("npm run build", shell=True)
    subprocess.run("npx cap add android", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("npx cap copy android", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("npx cap sync android", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    storage_permissions = ["android.permission.READ_EXTERNAL_STORAGE", "android.permission.WRITE_EXTERNAL_STORAGE", "android.permission.MANAGE_EXTERNAL_STORAGE"]
    if any(perm in selected_perm for perm in storage_permissions):
        install_filesystem_plugin(working_dir)
    build_gradle_path = os.path.join(abs_dir, "android", "app", "build.gradle")
    if os.path.exists(build_gradle_path):
        modify_build_gradle(build_gradle_path, version_code, version_name)
        create_proguard_rules(abs_dir)
        ensure_multidex_in_manifest(manifest_path)
    if selected_perm:
        add_permissions_to_manifest(manifest_path, selected_perm)
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
    print(f"\n{Colors.GREEN}[✓] Proses Setup Selesai!{Colors.END}")
    print(f"{Colors.CYAN}Informasi Aplikasi:{Colors.END}")
    print(f"Nama: {app_name}")
    print(f"App ID: {app_id}")
    print(f"Versi: {version_name} (code: {version_code})")
    print(f"Tipe Build: {'Debug' if build_type == '1' else 'Release'}")
    build_android(abs_dir, build_type)
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
        setup_html_project(temp_dir, app_name, app_id, version_name, version_code, selected_perm, fullscreen_mode, screen_orientation, build_type, icon_path if os.path.exists(icon_path) else None)
    elif project_type == 2:
        setup_react_project(temp_dir, app_name, app_id, version_name, version_code, selected_perm, fullscreen_mode, screen_orientation, build_type, icon_path if os.path.exists(icon_path) else None)
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
