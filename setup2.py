import os, json, zipfile, subprocess, shutil, re, sys
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
def add_permissions_to_manifest(abs_manifest_path, selected_perm):
    with open(abs_manifest_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r"\s*<!--\s*Permissions?\s*-->[\s\S]*?</manifest>\s*$", "\n</manifest>", content, flags=re.IGNORECASE)
    media_permissions = ["android.permission.READ_MEDIA_IMAGES", "android.permission.READ_MEDIA_VIDEO", "android.permission.READ_MEDIA_AUDIO"]
    has_media_permissions = any(perm in selected_perm for perm in media_permissions)
    permission_tags = []
    added_permissions = set()
    for perm in selected_perm:
        if perm in added_permissions:
            continue
        if perm == "android.permission.READ_EXTERNAL_STORAGE":
            permission_tags.append('<uses-permission android:maxSdkVersion="32" android:name="android.permission.READ_EXTERNAL_STORAGE"/>')
        elif perm == "android.permission.WRITE_EXTERNAL_STORAGE":
            permission_tags.append('<uses-permission android:maxSdkVersion="29" android:name="android.permission.WRITE_EXTERNAL_STORAGE"/>')
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
    if fullscreen_mode in ["1", "2"] and "android:theme" not in new_tag:
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
    with open(proguard_path, 'w') as f:
        f.write(rules)
def ensure_multidex_in_manifest(manifest_path):
    with open(manifest_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if 'android:name="androidx.multidex.MultiDexApplication"' not in content:
        content = re.sub(r'(<application\s+)', r'\1android:name="androidx.multidex.MultiDexApplication" ', content)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        f.write(content)
def modify_build_gradle(build_gradle_path, version_code, version_name):
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
def install_filesystem_plugin(working_dir):
    os.chdir(working_dir)
    if not os.path.exists("package.json"):
        return False
    subprocess.run("npm install @capacitor/filesystem", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("npx cap sync android", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True
def build_android(working_dir, build_type):
    root_dir = os.getcwd()
    android_dir = os.path.join(working_dir, "android")
    if not os.path.exists(android_dir):
        return False
    os.chdir(android_dir)
    subprocess.run("chmod +x gradlew", shell=True)
    cmd = "./gradlew assembleDebug" if build_type == "1" else "./gradlew assembleRelease"
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        pass
    process.wait()
    if process.returncode == 0:
        apk_name = "app-debug.apk" if build_type == "1" else "app-release.apk"
        apk_path = os.path.join(android_dir, "app", "build", "outputs", "apk", "debug" if build_type == "1" else "release", apk_name)
        if os.path.exists(apk_path):
            shutil.copy2(apk_path, os.path.join(root_dir, apk_name))
        return True
    return False
def find_icon_file(working_dir):
    icon_path = os.path.join(working_dir, "icon.png")
    if os.path.exists(icon_path):
        return icon_path
    for subdir in ["www", "build", "dist"]:
        path = os.path.join(working_dir, subdir, "icon.png")
        if os.path.exists(path):
            return path
    for root, dirs, files in os.walk(working_dir):
        if 'icon.png' in files:
            return os.path.join(root, 'icon.png')
    return None
def rewrite_main_activity(main_activity_path, fullscreen_mode, screen_orientation, app_id):
    orientation_code = ""
    if screen_orientation == "1":
        orientation_code = "setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT);"
    elif screen_orientation == "2":
        orientation_code = "setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);"
    fullscreen_code = ""
    if fullscreen_mode in ["1", "2"]:
        if fullscreen_mode == "1":
            behavior = "WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE"
        else:
            behavior = "WindowInsetsController.BEHAVIOR_SHOW_BARS_BY_TOUCH"
        fullscreen_code = f"""
        getWindow().setFlags(
            WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS
        );
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {{
            getWindow().setDecorFitsSystemWindows(false);
            WindowInsetsController controller = getWindow().getInsetsController();
            if (controller != null) {{
                controller.hide(WindowInsets.Type.systemBars());
                controller.setSystemBarsBehavior({behavior});
            }}
        }} else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {{
            getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            );
        }}"""
    java_code = f"""package {app_id};
import android.os.Bundle;
import android.view.WindowManager;
import android.view.View;
import android.os.Build;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.WebView;
import android.webkit.WebSettings;
{( "import android.content.pm.ActivityInfo;" if orientation_code else "" )}
import com.getcapacitor.BridgeActivity;
public class MainActivity extends BridgeActivity {{
    @Override
    protected void onCreate(Bundle savedInstanceState) {{
        super.onCreate(savedInstanceState);
        {fullscreen_code}
        {orientation_code}
        enableNativePerformance();
        requestAppPermissions();
    }}
    
    private void enableNativePerformance() {{
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {{
            WebView.setWebContentsDebuggingEnabled(true);
            getBridge().getWebView().setLayerType(View.LAYER_TYPE_HARDWARE, null);
            getBridge().getWebView().setDrawingCacheEnabled(true);
        }}
        
        getBridge().getWebView().getSettings().setCacheMode(WebSettings.LOAD_DEFAULT);
        getBridge().getWebView().getSettings().setRenderPriority(WebSettings.RenderPriority.HIGH);
        getBridge().getWebView().getSettings().setUseWideViewPort(true);
        getBridge().getWebView().getSettings().setLoadWithOverviewMode(true);
        getBridge().getWebView().getSettings().setDomStorageEnabled(true);
        getBridge().getWebView().getSettings().setDatabaseEnabled(true);
    }}
    
    private void requestAppPermissions() {{
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) {{
            return;
        }}
        java.util.ArrayList<String> permissionsToRequest = new java.util.ArrayList<>();
        if (checkSelfPermission(android.Manifest.permission.INTERNET) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.INTERNET);
        }}
        if (checkSelfPermission(android.Manifest.permission.CAMERA) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.CAMERA);
        }}
        if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.RECORD_AUDIO);
        }}
        if (checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.ACCESS_FINE_LOCATION);
        }}
        if (checkSelfPermission(android.Manifest.permission.ACCESS_COARSE_LOCATION) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.ACCESS_COARSE_LOCATION);
        }}
        if (checkSelfPermission(android.Manifest.permission.READ_EXTERNAL_STORAGE) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.READ_EXTERNAL_STORAGE);
        }}
        if (checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.WRITE_EXTERNAL_STORAGE);
        }}
        if (checkSelfPermission(android.Manifest.permission.MANAGE_EXTERNAL_STORAGE) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.MANAGE_EXTERNAL_STORAGE);
        }}
        if (checkSelfPermission(android.Manifest.permission.READ_MEDIA_IMAGES) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.READ_MEDIA_IMAGES);
        }}
        if (checkSelfPermission(android.Manifest.permission.READ_MEDIA_VIDEO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.READ_MEDIA_VIDEO);
        }}
        if (checkSelfPermission(android.Manifest.permission.READ_MEDIA_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.READ_MEDIA_AUDIO);
        }}
        if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.POST_NOTIFICATIONS);
        }}
        if (checkSelfPermission(android.Manifest.permission.READ_CONTACTS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.READ_CONTACTS);
        }}
        if (checkSelfPermission(android.Manifest.permission.WRITE_CONTACTS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.WRITE_CONTACTS);
        }}
        if (checkSelfPermission(android.Manifest.permission.READ_CALENDAR) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.READ_CALENDAR);
        }}
        if (checkSelfPermission(android.Manifest.permission.WRITE_CALENDAR) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.WRITE_CALENDAR);
        }}
        if (checkSelfPermission(android.Manifest.permission.SEND_SMS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.SEND_SMS);
        }}
        if (checkSelfPermission(android.Manifest.permission.READ_PHONE_STATE) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.READ_PHONE_STATE);
        }}
        if (checkSelfPermission(android.Manifest.permission.CALL_PHONE) != android.content.pm.PackageManager.PERMISSION_GRANTED) {{
            permissionsToRequest.add(android.Manifest.permission.CALL_PHONE);
        }}
        if (!permissionsToRequest.isEmpty()) {{
            requestPermissions(permissionsToRequest.toArray(new String[0]), 100);
        }}
    }}
}}
"""
    with open(main_activity_path, "w", encoding="utf-8") as f:
        f.write(java_code)
def create_permissions_js(working_dir, project_type):
    permissions_js_content = """// File untuk menangani izin runtime (jika diperlukan)
// Capacitor v3+ menggunakan pendekatan yang berbeda untuk permissions
import { App } from '@capacitor/app';

export async function checkAndRequestPermissions() {
  try {
    console.log('Memeriksa dan meminta izin jika diperlukan');
    return true;
  } catch (error) {
    console.error('Error dalam permission handling:', error);
    return false;
  }
}

export function initializePermissions() {
  setTimeout(async () => {
    try {
      await checkAndRequestPermissions();
      console.log('Permission initialization completed');
    } catch (error) {
      console.error('Error initializing permissions:', error);
    }
  }, 3000);
}

export function setupBackButtonHandler() {
  App.addListener('backButton', ({ canGoBack }) => {
    if (!canGoBack) {
      App.exitApp();
    } else {
      window.history.back();
    }
  });
}

export function showPermissionAlert(message) {
  if (typeof alert !== 'undefined') {
    alert(message);
  } else if (typeof window !== 'undefined' && window.alert) {
    window.alert(message);
  } else {
    console.log('ALERT:', message);
  }
}
"""
    if project_type == 1:
        js_dir = os.path.join(working_dir, "www", "js")
        os.makedirs(js_dir, exist_ok=True)
        with open(os.path.join(js_dir, "permissions.js"), "w", encoding="utf-8") as f:
            f.write(permissions_js_content)
    else:
        js_dir = os.path.join(working_dir, "src", "utils")
        os.makedirs(js_dir, exist_ok=True)
        with open(os.path.join(js_dir, "permissions.js"), "w", encoding="utf-8") as f:
            f.write(permissions_js_content)
def add_permissions_script_to_index(working_dir, project_type):
    if project_type == 1:
        index_path = os.path.join(working_dir, "www", "index.html")
        if not os.path.exists(index_path):
            return
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
        if 'js/permissions.js' not in content:
            permissions_script = '\n    <script src="js/permissions.js"></script>\n    <script>initializePermissions();</script>\n</body>'
            content = content.replace('</body>', permissions_script)
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(content)
    else:
        app_jsx_path = os.path.join(working_dir, "src", "App.jsx")
        app_js_path = os.path.join(working_dir, "src", "App.js")
        app_tsx_path = os.path.join(working_dir, "src", "App.tsx")
        app_ts_path = os.path.join(working_dir, "src", "App.ts")
        target_file = None
        for file_path in [app_jsx_path, app_js_path, app_tsx_path, app_ts_path]:
            if os.path.exists(file_path):
                target_file = file_path
                break
        if not target_file:
            return
        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()
        if 'initializePermissions' in content:
            return
        setup_permissions_path = os.path.join(working_dir, "src", "setupPermissions.js")
        setup_content = """import { initializePermissions, setupBackButtonHandler } from './utils/permissions';
// Initialize permissions when app starts
initializePermissions();
setupBackButtonHandler();
export default function setupPermissions() {
  // Function kosong, hanya untuk import side effects
}
"""
        with open(setup_permissions_path, "w", encoding="utf-8") as f:
            f.write(setup_content)
        main_files = [
            os.path.join(working_dir, "src", "main.jsx"),
            os.path.join(working_dir, "src", "main.js"),
            os.path.join(working_dir, "src", "index.jsx"),
            os.path.join(working_dir, "src", "index.js"),
            os.path.join(working_dir, "src", "main.tsx"),
            os.path.join(working_dir, "src", "main.ts"),
            os.path.join(working_dir, "src", "index.tsx"),
            os.path.join(working_dir, "src", "index.ts")
        ]
        main_file = None
        for file_path in main_files:
            if os.path.exists(file_path):
                main_file = file_path
                break
        if main_file:
            with open(main_file, "r", encoding="utf-8") as f:
                main_content = f.read()
            if 'setupPermissions' not in main_content:
                import_line = "import './setupPermissions';"
                lines = main_content.split('\n')
                insert_index = 0
                for i, line in enumerate(lines):
                    if line.strip().startswith('import '):
                        insert_index = i + 1
                    elif line.strip() and not line.strip().startswith('//'):
                        break
                lines.insert(insert_index, import_line)
                main_content = '\n'.join(lines)
                with open(main_file, "w", encoding="utf-8") as f:
                    f.write(main_content)
        else:
            lines = content.split('\n')
            import_line = "import { initializePermissions } from './utils/permissions';"
            last_import_index = -1
            for i, line in enumerate(lines):
                if line.strip().startswith('import '):
                    last_import_index = i
            if last_import_index != -1:
                lines.insert(last_import_index + 1, import_line)
            else:
                lines.insert(0, import_line)
            for i, line in enumerate(lines):
                if 'function App()' in line or 'const App =' in line:
                    for j in range(i, len(lines)):
                        if '{' in lines[j]:
                            useEffect_code = """  useEffect(() => {
    initializePermissions();
    setupBackButtonHandler();
  }, []);"""
                            lines.insert(j + 1, useEffect_code)
                            break
                    break
            content = '\n'.join(lines)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)
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
def replace_images(project_dir, image_path):
    if not image_path or not os.path.exists(image_path):
        return
    res_path = os.path.join(project_dir, "android", "app", "src", "main", "res")
    scan_and_replace_with_webp(res_path, image_path)
def setup_project(working_dir, app_name, app_id, version_name, version_code, selected_perm, fullscreen_mode, screen_orientation, build_type, image_path, project_type):
    abs_dir = os.path.abspath(working_dir)
    manifest_path = os.path.join(abs_dir, "android", "app", "src", "main", "AndroidManifest.xml")
    web_dir = "www" if project_type == 1 else "build"
    if project_type == 1:
        if not os.path.exists("www"):
            os.makedirs("www", exist_ok=True)
        for item in os.listdir("."):
            if item not in ["www", "node_modules", "icon.png", "config.json", os.path.basename(__file__)]:
                try:
                    shutil.move(item, os.path.join("www", item))
                except:
                    pass
        subprocess.run("npm init -y", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run("npm run build", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run("npm install @capacitor/core @capacitor/cli @capacitor/android @capacitor/app", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(f'npx cap init "{app_name}" "{app_id}" --web-dir {web_dir}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        rewrite_main_activity(main_activity_path, fullscreen_mode, screen_orientation, app_id)
    create_permissions_js(working_dir, project_type)
    add_permissions_script_to_index(working_dir, project_type)
    if image_path and os.path.exists(image_path):
        replace_images(abs_dir, image_path)
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
    setup_project(temp_dir, app_name, app_id, version_name, version_code, selected_perm, fullscreen_mode, screen_orientation, build_type, icon_path if os.path.exists(icon_path) else None, project_type)
def tool2_builder():
    current_dir = os.getcwd()
    zip_path = os.path.join(current_dir, "game.capzip")
    if os.path.exists(zip_path):
        extract_and_setup(zip_path)
if __name__ == "__main__":
    tool2_builder()
