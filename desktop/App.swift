import AppKit
import AVFoundation
import WebKit

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var status: NSTextField!
    private var runtime: Process?
    private var timer: Timer?
    private var baseURL: URL?
    private var instance = ""
    private var quitting = false
    private var startedAt = Date()
    private let dataURL: URL = {
        if let path = ProcessInfo.processInfo.environment["CLASSECHO_DESKTOP_DATA_DIR"] {
            return URL(fileURLWithPath: path, isDirectory: true)
        }
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("ClassEcho/data", isDirectory: true)
    }()

    func applicationDidFinishLaunching(_ notification: Notification) {
        let applicationMenu = NSMenu()
        applicationMenu.addItem(withTitle: "关于 ClassEcho", action: #selector(about), keyEquivalent: "")
        applicationMenu.addItem(.separator())
        applicationMenu.addItem(withTitle: "打开数据目录", action: #selector(openData), keyEquivalent: "")
        applicationMenu.addItem(withTitle: "打开日志目录", action: #selector(openLogs), keyEquivalent: "")
        applicationMenu.addItem(withTitle: "第三方许可与源码", action: #selector(openLicenses), keyEquivalent: "")
        applicationMenu.addItem(withTitle: "在浏览器中打开", action: #selector(openBrowser), keyEquivalent: "")
        applicationMenu.addItem(.separator())
        applicationMenu.addItem(withTitle: "退出 ClassEcho", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let mainMenu = NSMenu()
        let item = NSMenuItem(); item.submenu = applicationMenu; mainMenu.addItem(item)
        let edit = NSMenu(title: "编辑")
        for (title, action, key) in [("撤销", "undo:", "z"), ("剪切", "cut:", "x"), ("复制", "copy:", "c"), ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] {
            edit.addItem(withTitle: title, action: Selector(action), keyEquivalent: key)
        }
        let editItem = NSMenuItem(); editItem.submenu = edit; mainMenu.addItem(editItem)
        NSApp.mainMenu = mainMenu

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1184, height: 800), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "ClassEcho"
        window.minSize = NSSize(width: 560, height: 520)
        window.delegate = self
        window.center()
        let configuration = WKWebViewConfiguration()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        webView = WKWebView(frame: window.contentView!.bounds, configuration: configuration)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self; webView.uiDelegate = self
        window.contentView!.addSubview(webView)
        status = NSTextField(wrappingLabelWithString: "正在启动本地工作区…")
        status.font = .systemFont(ofSize: 16)
        status.frame = NSRect(x: 32, y: 32, width: 600, height: 64)
        status.autoresizingMask = [.width, .maxYMargin]
        window.contentView!.addSubview(status)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startRuntime()
    }

    private func startRuntime() {
        do {
            try FileManager.default.createDirectory(at: dataURL.appendingPathComponent("logs"), withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            let resources = Bundle.main.resourceURL!
            let application = resources.appendingPathComponent("app")
            let process = Process()
            process.executableURL = resources.appendingPathComponent("python/bin/python3.11")
            instance = UUID().uuidString
            process.arguments = ["-B", application.appendingPathComponent("desktop/runtime.py").path, "--data-dir", dataURL.path, "--instance-id", instance]
            process.currentDirectoryURL = application
            var environment = ProcessInfo.processInfo.environment
            environment.removeValue(forKey: "PYTHONHOME")
            environment["PYTHONPATH"] = application.path
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONUNBUFFERED"] = "1"
            process.environment = environment
            let log = dataURL.appendingPathComponent("logs/desktop.log")
            if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil, attributes: [.posixPermissions: 0o600]) }
            let handle = try FileHandle(forWritingTo: log); try handle.seekToEnd()
            process.standardOutput = handle; process.standardError = handle
            runtime = process
            try process.run()
            try handle.close()
            startedAt = Date()
            timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
                DispatchQueue.main.async { self?.checkReady() }
            }
        } catch { failure("本地服务未能启动。请打开日志目录检查。") }
    }

    private func checkReady() {
        guard !quitting else { return }
        if runtime?.isRunning != true {
            timer?.invalidate(); failure("本地服务已经退出。数据仍保存在工作区，请检查日志后重新打开应用。")
            return
        }
        if baseURL != nil { return }
        if let data = try? Data(contentsOf: dataURL.appendingPathComponent(".desktop-ready.json")),
           let info = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           info["instance_id"] as? String == instance,
           let address = info["url"] as? String, let url = URL(string: address),
           url.scheme == "http", url.host == "127.0.0.1", url.port != nil {
            baseURL = url
            status.isHidden = true
            webView.load(URLRequest(url: url))
        } else if baseURL == nil && Date().timeIntervalSince(startedAt) > 45 {
            timer?.invalidate(); failure("本地服务启动超时。请打开日志目录检查。")
        }
    }

    private func isLocal(_ url: URL?) -> Bool {
        guard let url, let baseURL else { return false }
        return url.scheme == "http" && url.host == "127.0.0.1" && url.port == baseURL.port
    }
    private func failure(_ message: String) {
        status.isHidden = false; status.stringValue = message
        let alert = NSAlert(); alert.messageText = "ClassEcho 启动未完成"; alert.informativeText = message
        alert.addButton(withTitle: "打开日志"); alert.addButton(withTitle: "退出")
        alert.beginSheetModal(for: window) { response in
            if response == .alertFirstButtonReturn { self.openLogs() } else { NSApp.terminate(nil) }
        }
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil); return true
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool { NSApp.terminate(nil); return false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateCancel }
        quitting = true
        webView.evaluateJavaScript("(() => { const e = new Event('beforeunload', {cancelable:true}); window.dispatchEvent(e); return e.defaultPrevented; })()") { value, _ in
            if value as? Bool == true {
                let alert = NSAlert(); alert.messageText = "有未保存的内容或录音"
                alert.informativeText = "退出会放弃页面内尚未保存的内容。请先保存或下载录音。"
                alert.addButton(withTitle: "返回保存"); alert.addButton(withTitle: "退出")
                alert.beginSheetModal(for: self.window) { result in
                    if result == .alertFirstButtonReturn { self.quitting = false; NSApp.reply(toApplicationShouldTerminate: false) }
                    else { self.stopRuntime() }
                }
            } else { self.stopRuntime() }
        }
        return .terminateLater
    }
    private func stopRuntime() {
        timer?.invalidate()
        status.isHidden = false; status.stringValue = "正在停止本地服务…"
        let process = runtime
        DispatchQueue.global().async {
            if let process, process.isRunning { process.terminate(); process.waitUntilExit() }
            DispatchQueue.main.async { NSApp.reply(toApplicationShouldTerminate: true) }
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if isLocal(navigationAction.request.url) || navigationAction.request.url?.scheme == "blob" { decisionHandler(navigationAction.shouldPerformDownload ? .download : .allow) }
        else { decisionHandler(.cancel); if let url = navigationAction.request.url, ["https", "http"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) } }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        let attachment = (navigationResponse.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition")?.lowercased().contains("attachment") == true
        decisionHandler(attachment ? .download : .allow)
    }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel(); panel.nameFieldStringValue = suggestedFilename
        panel.beginSheetModal(for: window) { result in completionHandler(result == .OK ? panel.url : nil) }
    }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { result in completionHandler(result == .OK ? panel.urls : nil) }
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert(); alert.messageText = message; alert.addButton(withTitle: "确定"); alert.addButton(withTitle: "取消")
        alert.beginSheetModal(for: window) { result in completionHandler(result == .alertFirstButtonReturn) }
    }
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert(); alert.messageText = message
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        guard type == .microphone, origin.protocol == "http", origin.host == "127.0.0.1", origin.port == baseURL?.port else { decisionHandler(.deny); return }
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: decisionHandler(.grant)
        case .notDetermined: AVCaptureDevice.requestAccess(for: .audio) { allowed in DispatchQueue.main.async { decisionHandler(allowed ? .grant : .deny) } }
        default: decisionHandler(.deny)
        }
    }
    @objc private func openData() { NSWorkspace.shared.open(dataURL) }
    @objc private func openLogs() { NSWorkspace.shared.open(dataURL.appendingPathComponent("logs")) }
    @objc private func openLicenses() { NSWorkspace.shared.open(Bundle.main.resourceURL!.appendingPathComponent("licenses")) }
    @objc private func openBrowser() { if let baseURL { NSWorkspace.shared.open(baseURL) } }
    @objc private func about() {
        let alert = NSAlert(); alert.messageText = "ClassEcho · 桌面预览版"
        alert.informativeText = "Apple Silicon 本地课堂笔记工具。\n原创代码采用 MIT 许可。内含 CPython、MLX 等组件，以及 LGPL FFmpeg 和 AGPLv3 Redis；对应许可与工具源码可从应用菜单查看。\n本预览包使用本地签名，尚未进行 Apple 公证。"
        alert.beginSheetModal(for: window)
    }
}

@main
struct ClassEchoApplication {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { app.run() }
    }
}
