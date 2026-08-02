import 'dart:convert';
import 'dart:math' as math;
import 'package:http/http.dart' as http;
import '../app_config.dart';
import 'session_store.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class ApiService {
  ApiService({SessionStore? sessionStore})
    : _sessionStore = sessionStore ?? SessionStore();

  final SessionStore _sessionStore;
  bool _previewSignedIn = true;
  int _previewScanCount = 20383;
  bool _previewAlpacaConnected = true;

  final List<Map<String, dynamic>> _previewWatchlist = [
    {'ticker': 'AAPL', 'notes': 'Quality momentum setup'},
    {'ticker': 'NVDA', 'notes': 'Watching resistance breakout'},
    {'ticker': 'MSFT', 'notes': 'Long-term trend remains constructive'},
  ];

  final List<Map<String, dynamic>> _previewPaperTrades = [
    {
      'ticker': 'AAPL',
      'status': 'OPEN',
      'direction': 'LONG',
      'size': 12,
      'entry_price': 221.40,
      'current_price': 228.16,
      'current_pnl': 81.12,
      'current_pnl_pct': 3.05,
      'success_label': 'IN PROGRESS',
    },
    {
      'ticker': 'NVDA',
      'status': 'OPEN',
      'direction': 'LONG',
      'size': 8,
      'entry_price': 171.25,
      'current_price': 176.92,
      'current_pnl': 45.36,
      'current_pnl_pct': 3.31,
      'success_label': 'IN PROGRESS',
    },
    {
      'ticker': 'TSLA',
      'status': 'CLOSED',
      'direction': 'SHORT',
      'size': 5,
      'entry_price': 334.10,
      'current_price': 329.45,
      'close_price': 326.80,
      'pnl': 36.50,
      'pnl_pct': 2.18,
      'success': true,
      'success_label': 'YES',
    },
  ];

  Uri _uri(String path) => Uri.parse('${AppConfig.apiBaseUrl}$path');

  Future<void> _previewPause([int milliseconds = 280]) =>
      Future<void>.delayed(Duration(milliseconds: milliseconds));

  Future<Map<String, String>> _headers({bool jsonBody = false}) async {
    final token = await _sessionStore.readToken();
    return {
      'Accept': 'application/json',
      if (jsonBody) 'Content-Type': 'application/json',
      if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
    };
  }

  dynamic _decode(http.Response response) {
    dynamic data;
    try {
      data = jsonDecode(response.body);
    } catch (_) {
      data = response.body;
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      var message = 'Request failed (${response.statusCode}).';
      if (data is Map && data['detail'] != null) {
        final detail = data['detail'];
        message = detail is Map
            ? (detail['message']?.toString() ?? detail.toString())
            : detail.toString();
      }
      throw ApiException(message, statusCode: response.statusCode);
    }
    return data;
  }

  Map<String, dynamic> _previewUser({String? email, String? displayName}) => {
    'user': {
      'display_name': displayName?.isNotEmpty == true
          ? displayName
          : 'Oryntra Preview',
      'email': email?.isNotEmpty == true ? email : 'preview@oryntra.local',
    },
    'token': 'oryntra-preview-token',
  };

  Future<Map<String, dynamic>> signup(
    String email,
    String password,
    String displayName,
  ) async {
    if (AppConfig.previewMode) {
      await _previewPause();
      _previewSignedIn = true;
      await _sessionStore.saveToken('oryntra-preview-token');
      return _previewUser(email: email, displayName: displayName);
    }
    final response = await http
        .post(
          _uri('/api/auth/signup'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'email': email,
            'password': password,
            'display_name': displayName,
          }),
        )
        .timeout(const Duration(seconds: 20));
    final data = Map<String, dynamic>.from(_decode(response) as Map);
    final token = data['token']?.toString();
    if (token != null && token.isNotEmpty) await _sessionStore.saveToken(token);
    return data;
  }

  Future<void> deleteAccount(String password) async {
    if (AppConfig.previewMode) {
      await _previewPause();
      _previewSignedIn = false;
      await _sessionStore.clear();
      return;
    }
    final response = await http
        .delete(
          _uri('/api/auth/account'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'password': password}),
        )
        .timeout(const Duration(seconds: 20));
    _decode(response);
    await _sessionStore.clear();
  }

  Future<Map<String, dynamic>> login(String email, String password) async {
    if (AppConfig.previewMode) {
      await _previewPause();
      _previewSignedIn = true;
      await _sessionStore.saveToken('oryntra-preview-token');
      return _previewUser(email: email);
    }
    final response = await http
        .post(
          _uri('/api/auth/login'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'email': email, 'password': password}),
        )
        .timeout(const Duration(seconds: 20));
    final data = Map<String, dynamic>.from(_decode(response) as Map);
    final token = data['token']?.toString();
    if (token != null && token.isNotEmpty) await _sessionStore.saveToken(token);
    return data;
  }

  Future<Map<String, dynamic>?> me() async {
    if (AppConfig.previewMode) {
      await _previewPause(120);
      return _previewSignedIn ? _previewUser() : null;
    }
    final response = await http
        .get(_uri('/api/auth/me'), headers: await _headers())
        .timeout(const Duration(seconds: 15));
    if (response.statusCode == 401) return null;
    return Map<String, dynamic>.from(_decode(response) as Map);
  }

  Future<void> logout() async {
    if (AppConfig.previewMode) {
      await _previewPause(120);
      _previewSignedIn = false;
      await _sessionStore.clear();
      return;
    }
    try {
      await http.post(_uri('/api/auth/logout'), headers: await _headers());
    } finally {
      await _sessionStore.clear();
    }
  }

  Future<Map<String, dynamic>> alpacaStatus() async {
    if (AppConfig.previewMode) {
      await _previewPause(160);
      return {
        'connected': _previewAlpacaConnected,
        'preferred_environment': _previewAlpacaConnected ? 'paper' : null,
        'connections': _previewAlpacaConnected
            ? [
                {
                  'environment': 'paper',
                  'account_status': 'ACTIVE',
                  'status': 'CONNECTED',
                  'account_last4': '1234',
                  'connected_at': DateTime.now().toIso8601String(),
                },
              ]
            : const [],
      };
    }
    final response = await http
        .get(_uri('/api/alpaca/status'), headers: await _headers())
        .timeout(const Duration(seconds: 20));
    return Map<String, dynamic>.from(_decode(response) as Map);
  }

  Future<Map<String, dynamic>> beginAlpacaConnect({
    String environment = 'paper',
  }) async {
    if (AppConfig.previewMode) {
      await _previewPause(220);
      _previewAlpacaConnected = true;
      return {
        'authorization_url': 'https://app.alpaca.markets',
        'environment': environment,
        'preview': true,
      };
    }
    final response = await http
        .post(
          _uri('/api/alpaca/connect/start'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'environment': environment}),
        )
        .timeout(const Duration(seconds: 20));
    return Map<String, dynamic>.from(_decode(response) as Map);
  }

  Future<void> disconnectAlpaca(String environment) async {
    if (AppConfig.previewMode) {
      await _previewPause(180);
      _previewAlpacaConnected = false;
      return;
    }
    final response = await http
        .delete(
          _uri('/api/alpaca/disconnect/${Uri.encodeComponent(environment)}'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 20));
    _decode(response);
  }

  List<Map<String, dynamic>> _previewPatterns(String ticker, int quality) {
    final names = [
      ['Ascending channel', 'BULLISH'],
      ['Descending channel', 'BEARISH'],
      ['Bull flag', 'BULLISH'],
      ['Bear flag', 'BEARISH'],
      ['Higher-low structure', 'BULLISH'],
      ['Lower-high structure', 'BEARISH'],
      ['Volume expansion', 'NEUTRAL'],
      ['Support retest', 'BULLISH'],
      ['Resistance rejection', 'BEARISH'],
      ['Rounded base', 'BULLISH'],
      ['Momentum compression', 'NEUTRAL'],
      ['Range breakout', 'BULLISH'],
    ];
    final seed = ticker.codeUnits.fold<int>(0, (a, b) => a * 31 + b);
    return List.generate(3, (index) {
      final item = names[(seed.abs() + index * 4) % names.length];
      return {
        'name': item[0],
        'bias': item[1],
        'confidence': math.max(
          52,
          math.min(94, quality - index * 8 + (seed.abs() % 7)),
        ),
      };
    });
  }

  Map<String, dynamic> _normalizeScanResult(Map<String, dynamic> data) {
    final tradePlan = data['trade_plan'];
    final setup = data['setup'];
    if (tradePlan is Map) {
      data['signal'] ??= tradePlan['signal'];
      data['quality_score'] ??= tradePlan['quality_score'];
      data['entry'] ??= tradePlan['entry_ideal'] ?? tradePlan['entry'];
      data['stop'] ??= tradePlan['stop'];
      data['target'] ??= tradePlan['target'];
    }
    if (setup is Map) {
      data['setup_type'] ??= setup['setup_type'] ?? setup['type'];
    }
    data['scan_count'] ??= data['search_counter'];
    return data;
  }

  Future<Map<String, dynamic>> scan(
    String ticker, {
    String period = '6mo',
  }) async {
    if (AppConfig.previewMode) {
      await _previewPause(650);
      if (!_previewAlpacaConnected) {
        throw ApiException(
          'Connect an Alpaca account from the Account tab before scanning.',
          statusCode: 409,
        );
      }
      final normalized = ticker.trim().toUpperCase();
      final seed = normalized.codeUnits.fold<int>(
        0,
        (sum, value) => sum * 37 + value,
      );
      final price = 55 + (seed.abs() % 330) + ((seed.abs() % 100) / 100);
      final quality = 61 + (seed.abs() % 35);
      final bullish = seed.isEven;
      final entry = price * (bullish ? 1.002 : .998);
      final stop = price * (bullish ? .956 : 1.044);
      final target = price * (bullish ? 1.094 : .906);
      _previewScanCount += 1;
      return {
        'ticker': normalized,
        'company_name': '$normalized Holdings',
        'period': period,
        'signal': bullish ? 'BULLISH' : 'BEARISH',
        'price': double.parse(price.toStringAsFixed(2)),
        'day_change': double.parse(
          ((bullish ? 1.84 : -1.37)).toStringAsFixed(2),
        ),
        'quality_score': quality,
        'setup': {
          'setup_type': bullish ? 'TREND_CONTINUATION' : 'REVERSAL_ATTEMPT',
          'direction': bullish ? 'LONG' : 'SHORT',
        },
        'trade_plan': {
          'signal': bullish ? 'BUY' : 'SELL',
          'quality_score': quality,
          'quality_grade': quality >= 90
              ? 'A'
              : quality >= 80
              ? 'B'
              : 'C',
          'entry_ideal': double.parse(entry.toStringAsFixed(2)),
          'stop': double.parse(stop.toStringAsFixed(2)),
          'target': double.parse(target.toStringAsFixed(2)),
          'risk_reward': 2.1 + (seed.abs() % 12) / 10,
        },
        'search_counter': _previewScanCount,
        'patterns': {'recent': _previewPatterns(normalized, quality)},
        'rsi14': double.parse((38 + (seed.abs() % 34) + .4).toStringAsFixed(1)),
        'trend': bullish ? 'UPTREND' : 'DOWNTREND',
        'trend_strength': 40 + seed.abs() % 58,
        'volume': {
          'ratio': double.parse(
            (.72 + (seed.abs() % 105) / 100).toStringAsFixed(2),
          ),
          'trend': seed.isEven ? 'RISING' : 'MIXED',
        },
        'levels': {
          'support_1': double.parse((price * .965).toStringAsFixed(2)),
          'resist_1': double.parse((price * 1.052).toStringAsFixed(2)),
        },
        'chart': {
          'provider': 'tradingview',
          'symbol': 'NASDAQ:$normalized',
          'interval': 'D',
        },
        'alpaca_environment': 'paper',
        'data_policy': {
          'user_authorized_provider': 'alpaca',
          'raw_bars_returned': false,
          'chart_provider': 'tradingview',
        },
      };
    }
    final response = await http
        .post(
          _uri('/api/alpaca/scan'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'ticker': ticker, 'period': period}),
        )
        .timeout(const Duration(seconds: 60));
    final data = Map<String, dynamic>.from(_decode(response) as Map);
    return _normalizeScanResult(data);
  }

  Future<List<dynamic>> watchlist() async {
    if (AppConfig.previewMode) {
      await _previewPause();
      return _previewWatchlist
          .map<Map<String, dynamic>>((item) => Map<String, dynamic>.from(item))
          .toList();
    }
    final response = await http
        .get(_uri('/api/watchlist/'), headers: await _headers())
        .timeout(const Duration(seconds: 15));
    return List<dynamic>.from(_decode(response) as List);
  }

  Future<void> addWatchlist(String ticker) async {
    if (AppConfig.previewMode) {
      await _previewPause(180);
      final normalized = ticker.trim().toUpperCase();
      final exists = _previewWatchlist.any(
        (item) => item['ticker']?.toString().toUpperCase() == normalized,
      );
      if (!exists) {
        _previewWatchlist.insert(0, {
          'ticker': normalized,
          'notes': 'Added during browser preview',
        });
      }
      return;
    }
    final response = await http
        .post(
          _uri('/api/watchlist/add'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'ticker': ticker, 'notes': ''}),
        )
        .timeout(const Duration(seconds: 15));
    _decode(response);
  }

  Future<void> removeWatchlist(String ticker) async {
    if (AppConfig.previewMode) {
      await _previewPause(120);
      _previewWatchlist.removeWhere(
        (item) =>
            item['ticker']?.toString().toUpperCase() == ticker.toUpperCase(),
      );
      return;
    }
    final response = await http
        .delete(
          _uri('/api/watchlist/${Uri.encodeComponent(ticker)}'),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 15));
    _decode(response);
  }

  Future<List<dynamic>> paperTrades() async {
    if (AppConfig.previewMode) {
      await _previewPause();
      if (!_previewSignedIn) return const [];
      return _previewPaperTrades
          .map<Map<String, dynamic>>(
            (trade) => Map<String, dynamic>.from(trade),
          )
          .toList();
    }
    final response = await http
        .get(_uri('/api/paper/trades/all'), headers: await _headers())
        .timeout(const Duration(seconds: 30));
    return List<dynamic>.from(_decode(response) as List);
  }

  Future<Map<String, dynamic>> openPaperTrade({
    required String ticker,
    required String direction,
    required double entryPrice,
    required double stopPrice,
    required double targetPrice,
    required double size,
    String notes = '',
    String? setupType,
    double? qualityScore,
  }) async {
    final payload = {
      'ticker': ticker.trim().toUpperCase(),
      'direction': direction.trim().toUpperCase(),
      'entry_price': entryPrice,
      'stop_price': stopPrice,
      'target_price': targetPrice,
      'size': size,
      'notes': notes,
      'setup_type': setupType,
      'quality_score': qualityScore,
    };
    if (AppConfig.previewMode) {
      await _previewPause(240);
      if (!_previewSignedIn) {
        throw ApiException(
          'Create an account before opening a paper trade.',
          statusCode: 401,
        );
      }
      final trade = <String, dynamic>{
        'id': DateTime.now().microsecondsSinceEpoch,
        ...payload,
        'status': 'OPEN',
        'current_price': entryPrice,
        'current_pnl': 0.0,
        'current_pnl_pct': 0.0,
        'success_label': 'IN PROGRESS',
      };
      _previewPaperTrades.insert(0, trade);
      return Map<String, dynamic>.from(trade);
    }
    final response = await http
        .post(
          _uri('/api/paper/open'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode(payload),
        )
        .timeout(const Duration(seconds: 20));
    final decoded = _decode(response);
    return decoded is Map
        ? Map<String, dynamic>.from(decoded)
        : <String, dynamic>{'status': 'ok'};
  }

  Future<void> registerPushDevice({
    required String token,
    required String environment,
  }) async {
    if (AppConfig.previewMode) return;
    final response = await http
        .post(
          _uri('/api/notifications/device'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({
            'device_token': token,
            'environment': environment,
            'bundle_id': 'com.silascowles.oryntraai.app',
          }),
        )
        .timeout(const Duration(seconds: 15));
    _decode(response);
  }

  Future<void> addStockAlertSubscription(String ticker) async {
    if (AppConfig.previewMode) return;
    final response = await http
        .post(
          _uri('/api/notifications/stocks'),
          headers: await _headers(jsonBody: true),
          body: jsonEncode({'ticker': ticker.trim().toUpperCase()}),
        )
        .timeout(const Duration(seconds: 15));
    _decode(response);
  }

  Future<List<String>> stockAlertSubscriptions() async {
    if (AppConfig.previewMode) return const [];
    final response = await http
        .get(_uri('/api/notifications/stocks'), headers: await _headers())
        .timeout(const Duration(seconds: 15));
    final decoded = _decode(response);
    if (decoded is! List) return const [];
    return decoded
        .whereType<Map>()
        .map((item) => item['ticker']?.toString().trim().toUpperCase() ?? '')
        .where((ticker) => ticker.isNotEmpty)
        .toList();
  }

  Future<void> removeStockAlertSubscription(String ticker) async {
    if (AppConfig.previewMode) return;
    final response = await http
        .delete(
          _uri(
            '/api/notifications/stocks/${Uri.encodeComponent(ticker.trim().toUpperCase())}',
          ),
          headers: await _headers(),
        )
        .timeout(const Duration(seconds: 15));
    _decode(response);
  }
}
