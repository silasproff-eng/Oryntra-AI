import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum MarketAlertAddResult {
  added,
  alreadyAdded,
  limitReached,
  permissionDenied,
}

class NotificationService {
  static const _channel = MethodChannel('oryntra/notifications');
  static const _enabledKey = 'oryntra_notifications_enabled';
  static const _dailyKey = 'oryntra_daily_reminder_enabled';
  static const _marketTickersKey = 'oryntra_market_alert_tickers';
  static const marketAlertLimit = 5;

  Future<bool> isEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_enabledKey) ?? false;
  }

  Future<bool> isDailyReminderEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_dailyKey) ?? false;
  }

  Future<List<String>> marketAlertTickers() async {
    final prefs = await SharedPreferences.getInstance();
    final tickers = prefs.getStringList(_marketTickersKey) ?? const <String>[];
    return tickers
        .map((ticker) => ticker.trim().toUpperCase())
        .where((ticker) => ticker.isNotEmpty)
        .toSet()
        .take(marketAlertLimit)
        .toList();
  }

  Future<Map<String, String>?> pushRegistration() async {
    if (kIsWeb) return null;
    try {
      final raw = await _channel.invokeMapMethod<String, dynamic>(
        'pushRegistration',
      );
      final token = raw?['token']?.toString() ?? '';
      final environment = raw?['environment']?.toString() ?? '';
      if (token.isEmpty || environment.isEmpty) return null;
      return {'token': token, 'environment': environment};
    } on MissingPluginException {
      return null;
    }
  }

  Future<String> authorizationStatus() async {
    if (kIsWeb) return 'preview only';
    try {
      return await _channel.invokeMethod<String>('status') ?? 'unknown';
    } on MissingPluginException {
      return 'unsupported';
    }
  }

  Future<bool> requestPermission() async {
    final prefs = await SharedPreferences.getInstance();
    if (kIsWeb) {
      await prefs.setBool(_enabledKey, true);
      return true;
    }
    try {
      final granted =
          await _channel.invokeMethod<bool>('requestPermission') ?? false;
      await prefs.setBool(_enabledKey, granted);
      if (granted) await _restoreSchedules();
      return granted;
    } on MissingPluginException {
      await prefs.setBool(_enabledKey, false);
      return false;
    }
  }

  Future<void> setEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    if (!enabled) {
      if (!kIsWeb) {
        try {
          await _channel.invokeMethod<void>('cancelAll');
        } on MissingPluginException {
          
        }
      }
      await prefs.setBool(_dailyKey, false);
    }
    await prefs.setBool(_enabledKey, enabled);
  }

  Future<void> setDailyReminder(
    bool enabled, {
    int hour = 9,
    int minute = 30,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    if (enabled) {
      final allowed = await requestPermission();
      if (!allowed) return;
      if (!kIsWeb) {
        try {
          await _channel.invokeMethod<void>('scheduleDaily', {
            'hour': hour,
            'minute': minute,
          });
        } on MissingPluginException {
          return;
        }
      }
    } else if (!kIsWeb) {
      try {
        await _channel.invokeMethod<void>('cancelDaily');
      } on MissingPluginException {
        
      }
    }
    await prefs.setBool(_dailyKey, enabled);
  }

  Future<MarketAlertAddResult> addMarketAlert(String ticker) async {
    final normalized = ticker.trim().toUpperCase();
    if (normalized.isEmpty) return MarketAlertAddResult.alreadyAdded;
    final current = await marketAlertTickers();
    if (current.contains(normalized)) return MarketAlertAddResult.alreadyAdded;
    if (current.length >= marketAlertLimit) {
      return MarketAlertAddResult.limitReached;
    }
    if (!await requestPermission()) {
      return MarketAlertAddResult.permissionDenied;
    }
    final updated = [...current, normalized];
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_marketTickersKey, updated);
    await _syncMarketAlertReminders(updated);
    return MarketAlertAddResult.added;
  }

  Future<void> removeMarketAlert(String ticker) async {
    final normalized = ticker.trim().toUpperCase();
    final updated = await marketAlertTickers();
    updated.removeWhere((item) => item == normalized);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_marketTickersKey, updated);
    await _syncMarketAlertReminders(updated);
  }

  Future<void> clearMarketAlerts() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_marketTickersKey);
    await _syncMarketAlertReminders(const []);
  }

  Future<void> replaceMarketAlerts(List<String> tickers) async {
    final normalized = tickers
        .map((ticker) => ticker.trim().toUpperCase())
        .where((ticker) => ticker.isNotEmpty)
        .toSet()
        .take(marketAlertLimit)
        .toList();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_marketTickersKey, normalized);
    await _syncMarketAlertReminders(normalized);
  }

  Future<void> _restoreSchedules() async {
    final prefs = await SharedPreferences.getInstance();
    if (prefs.getBool(_dailyKey) ?? false) {
      try {
        await _channel.invokeMethod<void>('scheduleDaily', {
          'hour': 9,
          'minute': 30,
        });
      } on MissingPluginException {
        
      }
    }
    await _syncMarketAlertReminders(await marketAlertTickers());
  }

  Future<void> _syncMarketAlertReminders(List<String> tickers) async {
    if (kIsWeb) return;
    final prefs = await SharedPreferences.getInstance();
    final enabled = prefs.getBool(_enabledKey) ?? false;
    try {
      await _channel.invokeMethod<void>('syncMarketAlerts', {
        'tickers': enabled ? tickers : const <String>[],
      });
    } on MissingPluginException {
      
    }
  }

  Future<void> showScanResult({
    required String ticker,
    required String signal,
    required String quality,
  }) async {
    if (!await isEnabled() || kIsWeb) return;
    try {
      await _channel.invokeMethod<void>('showScanResult', {
        'ticker': ticker,
        'signal': signal,
        'quality': quality,
      });
    } on MissingPluginException {
      
    }
  }
}
