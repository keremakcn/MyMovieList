package com.moviewatchlist;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.util.Collections;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Native lifecycle and navigation around the shared, on-device film library. */
public class MainActivity extends Activity {
    private static final ExecutorService STARTUP = Executors.newSingleThreadExecutor();
    private WebView web;
    private FrameLayout root;
    private LinearLayout feedback;
    private volatile String origin;
    private boolean destroyed;
    private boolean failedLoad;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(16, 17, 22));
        setContentView(root);
        if (Build.VERSION.SDK_INT >= 30) getWindow().setDecorFitsSystemWindows(false);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                Insets safe = insets.getInsets(WindowInsets.Type.systemBars()
                    | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                view.setPadding(safe.left, safe.top, safe.right, safe.bottom);
                return WindowInsets.CONSUMED;
            } else {
                view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            }
            return insets.consumeSystemWindowInsets();
        });
        configureWebView();
        showFeedback("Opening your library…", false);
        startLibrary();
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(0, this::navigateBack);
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView() {
        web = new WebView(this);
        web.setBackgroundColor(Color.rgb(16, 17, 22));
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setBuiltInZoomControls(true);
        settings.setDisplayZoomControls(false);
        if (Build.VERSION.SDK_INT >= 26) settings.setSafeBrowsingEnabled(true);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        // No JavaScript-to-native bridge is exposed to page content.
        web.setWebViewClient(new WebViewClient() {
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                failedLoad = false;
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (isLocal(uri)) return false;
                if (request.isForMainFrame() && "https".equals(uri.getScheme())) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
                    catch (ActivityNotFoundException e) {
                        Toast.makeText(MainActivity.this, "No browser is available to open this link.", Toast.LENGTH_SHORT).show();
                    }
                }
                return true;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (isLocal(uri) || ("https".equals(uri.getScheme()) && "image.tmdb.org".equals(uri.getHost()))) return null;
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Blocked",
                    Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!failedLoad && origin != null && url.startsWith(origin + "/") && !url.contains("/_native/start")) {
                    hideFeedback();
                    // Bootstrap must not become a Back destination: it requires a native-only header.
                    if (view.getTag() == null) { view.clearHistory(); view.setTag(Boolean.TRUE); }
                }
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    failedLoad = true;
                    showFeedback("Your library could not be opened. Please try again.", true);
                }
            }
            @Override public boolean onRenderProcessGone(WebView view, android.webkit.RenderProcessGoneDetail detail) {
                root.removeView(web);
                web.destroy();
                configureWebView();
                showFeedback("The screen was closed by Android. Tap Retry to reopen your library.", true);
                return true;
            }
        });
        root.addView(web, 0, new FrameLayout.LayoutParams(-1, -1));
    }

    private boolean isLocal(Uri uri) {
        if (origin == null) return false;
        Uri base = Uri.parse(origin);
        return "http".equals(uri.getScheme()) && "127.0.0.1".equals(uri.getHost())
            && uri.getPort() == base.getPort() && uri.getUserInfo() == null;
    }

    private void startLibrary() {
        showFeedback("Opening your library…", false);
        STARTUP.execute(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                JSONObject connection = new JSONObject(Python.getInstance().getModule("android_bridge")
                    .callAttr("start", getFilesDir().getAbsolutePath()).toString());
                String url = connection.getString("url");
                String token = connection.getString("token");
                runOnUiThread(() -> {
                    if (destroyed) return;
                    origin = url;
                    web.setTag(null);
                    web.loadUrl(origin + "/_native/start", Collections.singletonMap("X-Native-Token", token));
                });
            } catch (Exception error) {
                android.util.Log.e("MovieWatchlist", "Library startup failed", error);
                runOnUiThread(() -> {
                    if (!destroyed) showFeedback("Your library could not be opened. Please try again.", true);
                });
            }
        });
    }

    private void showFeedback(String message, boolean retry) {
        hideFeedback();
        feedback = new LinearLayout(this);
        feedback.setOrientation(LinearLayout.VERTICAL);
        feedback.setGravity(Gravity.CENTER);
        feedback.setPadding(32, 32, 32, 32);
        feedback.setBackgroundColor(Color.rgb(16, 17, 22));
        TextView text = new TextView(this);
        text.setText(message);
        text.setTextColor(Color.rgb(244, 241, 236));
        text.setTextSize(18);
        text.setGravity(Gravity.CENTER);
        text.setPadding(0, 24, 0, 24);
        feedback.addView(text);
        if (retry) {
            Button button = new Button(this);
            button.setText(R.string.retry);
            button.setOnClickListener(v -> startLibrary());
            feedback.addView(button);
        } else feedback.addView(new ProgressBar(this));
        root.addView(feedback, new FrameLayout.LayoutParams(-1, -1));
    }

    private void hideFeedback() {
        if (feedback != null) { root.removeView(feedback); feedback = null; }
    }

    private void navigateBack() {
        if (web != null && web.canGoBack()) web.goBack();
        else moveTaskToBack(true);
    }

    // API 33+ uses the OnBackInvokedCallback registered in onCreate.
    // This fallback is required only for Android 7 through 12.
    @SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed() { navigateBack(); }
    @Override protected void onPause() { super.onPause(); if (web != null) web.onPause(); }
    @Override protected void onResume() { super.onResume(); if (web != null) web.onResume(); }
    @Override protected void onDestroy() {
        destroyed = true;
        if (web != null) { root.removeView(web); web.destroy(); }
        super.onDestroy();
    }
}
