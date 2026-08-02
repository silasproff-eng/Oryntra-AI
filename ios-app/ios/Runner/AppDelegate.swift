import Flutter
import UIKit
import UserNotifications
import WidgetKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private let appGroup = "group.silascowles.oryntraai"
  private var apnsDeviceToken: String?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    UNUserNotificationCenter.current().delegate = self
    registerForRemoteNotificationsIfAuthorized()

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    let messenger = engineBridge.applicationRegistrar.messenger()

    let notifications = FlutterMethodChannel(
      name: "oryntra/notifications",
      binaryMessenger: messenger
    )
    notifications.setMethodCallHandler { [weak self] call, result in
      self?.handleNotificationCall(call, result: result)
    }

    let widget = FlutterMethodChannel(
      name: "oryntra/widget",
      binaryMessenger: messenger
    )
    widget.setMethodCallHandler { [weak self] call, result in
      self?.handleWidgetCall(call, result: result)
    }

  }

  private func registerForRemoteNotificationsIfAuthorized() {
    UNUserNotificationCenter.current().getNotificationSettings { settings in
      switch settings.authorizationStatus {
      case .authorized, .provisional, .ephemeral:
        DispatchQueue.main.async {
          UIApplication.shared.registerForRemoteNotifications()
        }
      default:
        break
      }
    }
  }

  private func handleNotificationCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    let center = UNUserNotificationCenter.current()

    switch call.method {
    case "requestPermission":
      center.requestAuthorization(options: [.alert, .badge, .sound]) { granted, error in
        DispatchQueue.main.async {
          if let error = error {
            result(FlutterError(code: "notification_permission", message: error.localizedDescription, details: nil))
          } else {
            if granted {
              UIApplication.shared.registerForRemoteNotifications()
            }
            result(granted)
          }
        }
      }

    case "status":
      center.getNotificationSettings { settings in
        let value: String
        switch settings.authorizationStatus {
        case .authorized: value = "authorized"
        case .denied: value = "denied"
        case .provisional: value = "provisional"
        case .ephemeral: value = "ephemeral"
        case .notDetermined: value = "notDetermined"
        @unknown default: value = "unknown"
        }
        DispatchQueue.main.async { result(value) }
      }

    case "pushRegistration":
      guard let token = apnsDeviceToken else {
        result(nil)
        return
      }
      #if DEBUG
      let environment = "sandbox"
      #else
      let environment = "production"
      #endif
      result(["token": token, "environment": environment])

    case "scheduleDaily":
      guard let args = call.arguments as? [String: Any],
            let hour = args["hour"] as? Int,
            let minute = args["minute"] as? Int else {
        result(FlutterError(code: "invalid_arguments", message: "Hour and minute are required.", details: nil))
        return
      }
      center.removePendingNotificationRequests(withIdentifiers: dailyReminderIdentifiers)
      let requests = marketWeekdays.map { weekday in
        let content = UNMutableNotificationContent()
        content.title = "The U.S. market is opening"
        content.body = "Review your saved stocks or run a fresh educational market scan."
        content.sound = .default
        let components = easternMarketComponents(weekday: weekday, hour: hour, minute: minute)
        return UNNotificationRequest(
          identifier: "oryntra.daily.market.\(weekday)",
          content: content,
          trigger: UNCalendarNotificationTrigger(dateMatching: components, repeats: true)
        )
      }
      addNotificationRequests(requests, result: result)

    case "cancelDaily":
      center.removePendingNotificationRequests(withIdentifiers: dailyReminderIdentifiers)
      result(nil)

    case "syncMarketAlerts":
      guard let args = call.arguments as? [String: Any],
            let rawTickers = args["tickers"] as? [String] else {
        result(FlutterError(code: "invalid_arguments", message: "Tracked tickers are required.", details: nil))
        return
      }
      center.removePendingNotificationRequests(withIdentifiers: marketAlertIdentifiers)
      let tickers = rawTickers
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
        .filter { !$0.isEmpty }
      guard !tickers.isEmpty else {
        result(nil)
        return
      }
      let tickerList = tickers.prefix(5).joined(separator: ", ")
      let slots: [(hour: Int, minute: Int, title: String)] = [
        (9, 35, "Opening market check"),
        (12, 0, "Midday market check"),
        (16, 0, "Closing market check"),
      ]
      let requests = marketWeekdays.flatMap { weekday in
        slots.map { slot in
          let content = UNMutableNotificationContent()
          content.title = slot.title
          content.body = "Check \(tickerList) for today's percentage move and a fresh scan."
          content.sound = .default
          content.userInfo = ["oryntra_market_alert": true]
          let components = easternMarketComponents(
            weekday: weekday,
            hour: slot.hour,
            minute: slot.minute
          )
          return UNNotificationRequest(
            identifier: "oryntra.market.alert.\(weekday).\(slot.hour).\(slot.minute)",
            content: content,
            trigger: UNCalendarNotificationTrigger(dateMatching: components, repeats: true)
          )
        }
      }
      addNotificationRequests(requests, result: result)

    case "cancelAll":
      center.removeAllPendingNotificationRequests()
      center.removeAllDeliveredNotifications()
      result(nil)

    case "showScanResult":
      guard let args = call.arguments as? [String: Any] else {
        result(FlutterError(code: "invalid_arguments", message: "Scan details are required.", details: nil))
        return
      }
      let ticker = args["ticker"] as? String ?? "Ticker"
      let signal = args["signal"] as? String ?? "No signal"
      let quality = args["quality"] as? String ?? "—"
      let content = UNMutableNotificationContent()
      content.title = "\(ticker) scan complete"
      content.body = "Signal: \(signal) • Quality: \(quality). Educational analysis only."
      content.sound = .default
      let request = UNNotificationRequest(
        identifier: "oryntra.scan.\(UUID().uuidString)",
        content: content,
        trigger: nil
      )
      center.add(request) { error in
        DispatchQueue.main.async {
          if let error = error {
            result(FlutterError(code: "notification_delivery", message: error.localizedDescription, details: nil))
          } else {
            result(nil)
          }
        }
      }

    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private var marketWeekdays: [Int] { Array(2...6) }

  private var dailyReminderIdentifiers: [String] {
    marketWeekdays.map { "oryntra.daily.market.\($0)" } + ["oryntra.daily.market"]
  }

  private var marketAlertIdentifiers: [String] {
    let slots = [(9, 35), (12, 0), (16, 0)]
    return marketWeekdays.flatMap { weekday in
      slots.map { slot in
        let (hour, minute) = slot
        return "oryntra.market.alert.\(weekday).\(hour).\(minute)"
      }
    }
  }

  private func easternMarketComponents(weekday: Int, hour: Int, minute: Int) -> DateComponents {
    var components = DateComponents()
    components.calendar = Calendar(identifier: .gregorian)
    components.timeZone = TimeZone(identifier: "America/New_York")
    components.weekday = weekday
    components.hour = hour
    components.minute = minute
    return components
  }

  private func addNotificationRequests(
    _ requests: [UNNotificationRequest],
    result: @escaping FlutterResult
  ) {
    guard !requests.isEmpty else {
      result(nil)
      return
    }
    let group = DispatchGroup()
    let lock = NSLock()
    var firstError: Error?
    for request in requests {
      group.enter()
      UNUserNotificationCenter.current().add(request) { error in
        if let error = error {
          lock.lock()
          if firstError == nil { firstError = error }
          lock.unlock()
        }
        group.leave()
      }
    }
    group.notify(queue: .main) {
      if let error = firstError {
        result(FlutterError(code: "notification_schedule", message: error.localizedDescription, details: nil))
      } else {
        result(nil)
      }
    }
  }

  override func application(
    _ application: UIApplication,
    didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
  ) {
    super.application(application, didRegisterForRemoteNotificationsWithDeviceToken: deviceToken)
    let token = deviceToken.map { String(format: "%02x", $0) }.joined()
    apnsDeviceToken = token
    print("ORYNTRA APNS DEVICE TOKEN: \(token)")
  }

  override func application(
    _ application: UIApplication,
    didFailToRegisterForRemoteNotificationsWithError error: Error
  ) {
    super.application(application, didFailToRegisterForRemoteNotificationsWithError: error)
    print("ORYNTRA APNS REGISTRATION FAILED: \(error.localizedDescription)")
  }

  private func handleWidgetCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard call.method == "updateScan",
          let args = call.arguments as? [String: Any],
          let defaults = UserDefaults(suiteName: appGroup) else {
      result(FlutterMethodNotImplemented)
      return
    }

    defaults.set(args["ticker"] as? String ?? "—", forKey: "ticker")
    defaults.set(args["signal"] as? String ?? "—", forKey: "signal")
    defaults.set(args["price"] as? String ?? "—", forKey: "price")
    defaults.set(args["quality"] as? String ?? "—", forKey: "quality")
    defaults.set(args["updatedAt"] as? String ?? "", forKey: "updatedAt")
    defaults.synchronize()

    if #available(iOS 14.0, *) {
      WidgetCenter.shared.reloadAllTimelines()
    }
    result(nil)
  }

  override func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    willPresent notification: UNNotification,
    withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
  ) {
    completionHandler([.banner, .sound])
  }
}
