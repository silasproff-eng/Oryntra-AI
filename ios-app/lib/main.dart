import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'app_config.dart';
import 'screens/account_screen.dart';
import 'screens/paper_screen.dart';
import 'screens/scanner_screen.dart';
import 'screens/watchlist_screen.dart';
import 'services/api_service.dart';
import 'services/consent_service.dart';
import 'services/notification_service.dart';
import 'services/widget_service.dart';
import 'widgets/glass.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  final consent = ConsentService();
  await consent.gatherConsentAndInitializeAds();
  runApp(OryntraApp(consent: consent));
}

class OryntraApp extends StatefulWidget {
  const OryntraApp({super.key, required this.consent});
  final ConsentService consent;

  @override
  State<OryntraApp> createState() => _OryntraAppState();
}

class _OryntraAppState extends State<OryntraApp> {
  final _api = ApiService();
  final _notifications = NotificationService();
  final _widgetService = WidgetService();
  final _pages = PageController();
  final _scannerKey = GlobalKey<ScannerScreenState>();
  final _paperKey = GlobalKey<PaperScreenState>();
  final _accountKey = GlobalKey<AccountScreenState>();
  Map<String, dynamic>? _user;
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    _refreshUser();
  }

  @override
  void dispose() {
    _pages.dispose();
    super.dispose();
  }

  Future<void> _refreshUser() async {
    try {
      final result = await _api.me();
      final raw = result?['user'];
      if (raw is! Map) await _notifications.clearMarketAlerts();
      if (mounted) {
        setState(
          () => _user = raw is Map ? Map<String, dynamic>.from(raw) : null,
        );
      }
    } catch (_) {
      if (mounted) setState(() => _user = null);
    }
  }

  void _goTo(int value) {
    if (value == _tab || !_pages.hasClients) return;
    _pages.animateToPage(
      value,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeOutQuart,
    );
  }

  void _marketAlertsChanged() {
    _accountKey.currentState?.refreshNotificationSettings();
  }

  Future<void> _openCreateAccount() async {
    _goTo(3);
    await Future<void>.delayed(const Duration(milliseconds: 340));
    if (!mounted) return;
    await _accountKey.currentState?.showCreateAccount();
  }

  Future<void> _showPaperTrades() async {
    _goTo(2);
  }

  Future<void> _scanFromWatchlist(String ticker) async {
    _goTo(0);
    await Future<void>.delayed(const Duration(milliseconds: 460));
    if (!mounted) return;
    final scanner = _scannerKey.currentState;
    if (scanner != null) await scanner.scanTicker(ticker);
  }

  @override
  Widget build(BuildContext context) {
    final theme = ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme:
          ColorScheme.fromSeed(
            seedColor: OryntraPalette.blue,
            brightness: Brightness.dark,
          ).copyWith(
            primary: OryntraPalette.blueBright,
            onPrimary: OryntraPalette.deepNavy,
            surface: OryntraPalette.panel,
            onSurface: OryntraPalette.ink,
            error: OryntraPalette.danger,
          ),
      scaffoldBackgroundColor: OryntraPalette.deepNavy,
      dividerColor: OryntraPalette.rule,
      textTheme: Typography.material2021().white
          .apply(
            bodyColor: OryntraPalette.ink,
            displayColor: OryntraPalette.ink,
          )
          .copyWith(
            displaySmall: const TextStyle(
              fontSize: 34,
              height: 1.04,
              fontWeight: FontWeight.w800,
              letterSpacing: -1.1,
            ),
            headlineSmall: const TextStyle(
              fontSize: 24,
              height: 1.12,
              fontWeight: FontWeight.w800,
              letterSpacing: -.6,
            ),
            titleLarge: const TextStyle(
              fontSize: 20,
              height: 1.15,
              fontWeight: FontWeight.w800,
              letterSpacing: -.35,
            ),
            titleMedium: const TextStyle(
              fontSize: 16,
              height: 1.2,
              fontWeight: FontWeight.w700,
            ),
            bodyMedium: const TextStyle(
              fontSize: 14,
              height: 1.45,
              color: OryntraPalette.muted,
            ),
            bodySmall: const TextStyle(
              fontSize: 12,
              height: 1.4,
              color: OryntraPalette.muted,
            ),
          ),
      cardTheme: CardThemeData(
        color: OryntraPalette.panel,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: const BorderSide(color: OryntraPalette.rule),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: OryntraPalette.deepNavy.withValues(alpha: .62),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 15,
          vertical: 15,
        ),
        labelStyle: const TextStyle(color: OryntraPalette.muted),
        hintStyle: const TextStyle(color: Color(0xFF6E849C)),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: OryntraPalette.rule),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: OryntraPalette.rule),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(
            color: OryntraPalette.blueBright,
            width: 1.4,
          ),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: OryntraPalette.blueBright,
          foregroundColor: OryntraPalette.deepNavy,
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
          textStyle: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w800,
            letterSpacing: .1,
          ),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: OryntraPalette.deepNavy,
        side: const BorderSide(color: OryntraPalette.rule),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        labelStyle: const TextStyle(
          color: OryntraPalette.ink,
          fontWeight: FontWeight.w700,
        ),
      ),
    );

    final screens = [
      ScannerScreen(
        key: _scannerKey,
        api: _api,
        notifications: _notifications,
        widgetService: _widgetService,
        signedIn: _user != null,
        onCreateAccount: _openCreateAccount,
        onPaperTradeOpened: _showPaperTrades,
        onMarketAlertsChanged: _marketAlertsChanged,
      ),
      WatchlistScreen(
        api: _api,
        onScanTicker: _scanFromWatchlist,
        signedIn: _user != null,
        onCreateAccount: _openCreateAccount,
      ),
      PaperScreen(
        key: _paperKey,
        api: _api,
        signedIn: _user != null,
        onCreateAccount: _openCreateAccount,
      ),
      AccountScreen(
        key: _accountKey,
        api: _api,
        consent: widget.consent,
        user: _user,
        onAuthChanged: _refreshUser,
        notifications: _notifications,
      ),
    ];

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Oryntra AI',
      theme: theme,
      home: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: RadialGradient(
            center: Alignment(-.9, -1.15),
            radius: 1.45,
            colors: [
              Color(0xFF173B63),
              OryntraPalette.navy,
              OryntraPalette.deepNavy,
            ],
            stops: [0, .42, 1],
          ),
        ),
        child: Scaffold(
          backgroundColor: Colors.transparent,
          extendBody: true,
          appBar: AppBar(
            toolbarHeight: 66,
            backgroundColor: Colors.transparent,
            surfaceTintColor: Colors.transparent,
            title: Row(
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(10),
                  child: Image.asset(
                    'assets/oryntra-icon.png',
                    width: 36,
                    height: 36,
                    fit: BoxFit.cover,
                  ),
                ),
                const SizedBox(width: 10),
                const Text(
                  'Oryntra AI',
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    letterSpacing: -.7,
                  ),
                ),
                if (AppConfig.previewMode) ...[
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(999),
                      color: OryntraPalette.panelRaised,
                      border: Border.all(color: OryntraPalette.rule),
                    ),
                    child: Text(
                      'WEB PREVIEW · v${AppConfig.appVersion}',
                      style: TextStyle(
                        color: OryntraPalette.blueBright,
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
          body: SafeArea(
            bottom: false,
            child: PageView(
              controller: _pages,
              allowImplicitScrolling: true,
              physics: const PageScrollPhysics(parent: BouncingScrollPhysics()),
              onPageChanged: (value) {
                if (value != _tab) HapticFeedback.selectionClick();
                setState(() => _tab = value);
                if (value == 2 && _user != null) {
                  _paperKey.currentState?.refresh();
                } else if (value == 3) {
                  _accountKey.currentState?.refreshNotificationSettings();
                  _accountKey.currentState?.refreshProviderStatus();
                }
              },
              children: screens,
            ),
          ),
          bottomNavigationBar: GlassNavigationBar(
            index: _tab,
            onChanged: _goTo,
          ),
        ),
      ),
    );
  }
}
