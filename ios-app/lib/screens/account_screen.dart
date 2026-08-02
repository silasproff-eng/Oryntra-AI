import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../app_config.dart';
import '../services/api_service.dart';
import '../services/consent_service.dart';
import '../services/notification_service.dart';
import '../widgets/common.dart';
import '../widgets/glass.dart';

class AccountScreen extends StatefulWidget {
  const AccountScreen({
    super.key,
    required this.api,
    required this.consent,
    required this.user,
    required this.onAuthChanged,
    required this.notifications,
  });
  final ApiService api;
  final ConsentService consent;
  final Map<String, dynamic>? user;
  final VoidCallback onAuthChanged;
  final NotificationService notifications;

  @override
  State<AccountScreen> createState() => AccountScreenState();
}

class AccountScreenState extends State<AccountScreen> with WidgetsBindingObserver {
  bool _notificationsEnabled = false;
  bool _dailyReminderEnabled = false;
  String _notificationStatus = 'unknown';
  List<String> _marketAlerts = const [];
  Map<String, dynamic>? _alpacaStatus;
  bool _alpacaLoading = false;
  String? _alpacaError;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadNotificationSettings();
    _loadAlpacaStatus();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && widget.user != null) {
      _loadAlpacaStatus();
    }
  }

  @override
  void didUpdateWidget(covariant AccountScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.user == null && widget.user != null) {
      _syncMarketAlertsFromServer();
      _syncPushRegistration();
      _loadAlpacaStatus();
    } else if (oldWidget.user != null && widget.user == null) {
      setState(() {
        _alpacaStatus = null;
        _alpacaError = null;
      });
    }
  }

  Future<void> _loadNotificationSettings() async {
    final enabled = await widget.notifications.isEnabled();
    final daily = await widget.notifications.isDailyReminderEnabled();
    final status = await widget.notifications.authorizationStatus();
    final marketAlerts = await widget.notifications.marketAlertTickers();
    if (mounted) {
      setState(() {
        _notificationsEnabled = enabled;
        _dailyReminderEnabled = daily;
        _notificationStatus = status;
        _marketAlerts = marketAlerts;
      });
    }
  }

  Future<void> _loadAlpacaStatus() async {
    if (widget.user == null) {
      if (mounted) setState(() => _alpacaStatus = null);
      return;
    }
    setState(() {
      _alpacaLoading = true;
      _alpacaError = null;
    });
    try {
      final status = await widget.api.alpacaStatus();
      if (mounted) setState(() => _alpacaStatus = status);
    } catch (error) {
      if (mounted) setState(() => _alpacaError = error.toString());
    } finally {
      if (mounted) setState(() => _alpacaLoading = false);
    }
  }

  Future<void> refreshProviderStatus() => _loadAlpacaStatus();

  Future<void> _connectAlpaca(String environment) async {
    setState(() {
      _alpacaLoading = true;
      _alpacaError = null;
    });
    try {
      final result = await widget.api.beginAlpacaConnect(
        environment: environment,
      );
      if (AppConfig.previewMode) {
        await _loadAlpacaStatus();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Alpaca connection simulated in preview mode.')),
          );
        }
        return;
      }
      final rawUrl = result['authorization_url']?.toString() ?? '';
      final uri = Uri.tryParse(rawUrl);
      if (uri == null || !uri.hasScheme) {
        throw ApiException('The server did not return a valid Alpaca authorization URL.');
      }
      final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!opened) {
        throw ApiException('Could not open Alpaca authorization.');
      }
    } catch (error) {
      if (mounted) setState(() => _alpacaError = error.toString());
    } finally {
      if (mounted) setState(() => _alpacaLoading = false);
    }
  }

  Future<void> _disconnectAlpaca(String environment) async {
    setState(() {
      _alpacaLoading = true;
      _alpacaError = null;
    });
    try {
      await widget.api.disconnectAlpaca(environment);
      await _loadAlpacaStatus();
    } catch (error) {
      if (mounted) setState(() => _alpacaError = error.toString());
    } finally {
      if (mounted) setState(() => _alpacaLoading = false);
    }
  }

  List<Map<String, dynamic>> get _alpacaConnections {
    final raw = _alpacaStatus?['connections'];
    if (raw is! List) return const [];
    return raw
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<void> _toggleNotifications(bool enabled) async {
    if (enabled) {
      final granted = await widget.notifications.requestPermission();
      if (granted) {
        await Future<void>.delayed(const Duration(milliseconds: 750));
        await _syncPushRegistration();
      }
    } else {
      await widget.notifications.setEnabled(false);
    }
    await _loadNotificationSettings();
  }

  Future<void> _open(String url) =>
      launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);

  Future<void> _showAuth({bool create = false}) async {
    final changed = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _AuthSheet(api: widget.api, create: create),
    );
    if (changed == true) widget.onAuthChanged();
  }

  Future<void> showCreateAccount() => _showAuth(create: true);

  Future<void> refreshNotificationSettings() => _loadNotificationSettings();

  Future<void> _deleteAccount() async {
    final password = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Oryntra AI account?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'This permanently deletes your account, sessions, watchlist entries, subscriptions, and paper trades. This cannot be undone.',
            ),
            const SizedBox(height: 14),
            TextField(
              controller: password,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Confirm password'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
            child: const Text('Delete permanently'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await widget.api.deleteAccount(password.text);
      await widget.notifications.clearMarketAlerts();
      widget.onAuthChanged();
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Account deleted.')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.toString())));
      }
    }
  }

  Future<void> _removeMarketAlert(String ticker) async {
    await widget.notifications.removeMarketAlert(ticker);
    if (widget.user != null) {
      try {
        await widget.api.removeStockAlertSubscription(ticker);
      } on ApiException {
        // The on-device reminder is still removed if server sync is offline.
      }
    }
    await _loadNotificationSettings();
  }

  Future<void> _syncPushRegistration() async {
    if (widget.user == null) return;
    Map<String, String>? registration;
    for (var attempt = 0; attempt < 3 && registration == null; attempt++) {
      if (attempt > 0) {
        await Future<void>.delayed(Duration(seconds: attempt));
      }
      registration = await widget.notifications.pushRegistration();
    }
    if (registration == null) return;
    try {
      await widget.api.registerPushDevice(
        token: registration['token']!,
        environment: registration['environment']!,
      );
    } on ApiException {
      // Registration retries the next time the account or notification setting refreshes.
    }
  }

  Future<void> _syncMarketAlertsFromServer() async {
    if (widget.user == null) return;
    try {
      final remote = await widget.api.stockAlertSubscriptions();
      final local = await widget.notifications.marketAlertTickers();
      final merged = <String>{
        ...remote,
        ...local,
      }.take(NotificationService.marketAlertLimit).toList();
      for (final ticker in merged.where((ticker) => !remote.contains(ticker))) {
        await widget.api.addStockAlertSubscription(ticker);
      }
      await widget.notifications.replaceMarketAlerts(merged);
    } on ApiException {
      // Keep the on-device selection when the optional push endpoint is offline.
    }
    await _loadNotificationSettings();
  }

  Widget _buildAlpacaCard(BuildContext context) {
    final connections = _alpacaConnections;
    final connected = connections.any(
      (item) => item['status']?.toString().toUpperCase() == 'CONNECTED',
    );
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const Icon(Icons.link_rounded, color: Color(0xFF38CFF3)),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'Alpaca Connect',
                  style: TextStyle(fontWeight: FontWeight.w900, fontSize: 17),
                ),
              ),
              if (_alpacaLoading)
                const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else
                Icon(
                  connected ? Icons.check_circle : Icons.link_off_rounded,
                  color: connected
                      ? const Color(0xFF2DD4BF)
                      : Colors.white54,
                ),
            ],
          ),
          const SizedBox(height: 8),
          const Text(
            'Authorize read-only market data from your own Alpaca account. Oryntra never receives your Alpaca password and does not request trading permission.',
            style: TextStyle(fontSize: 12, color: Colors.white70),
          ),
          if (_alpacaError != null) ...[
            const SizedBox(height: 10),
            Text(
              _alpacaError!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          if (connections.isNotEmpty) ...[
            const SizedBox(height: 12),
            ...connections.map((connection) {
              final environment = connection['environment']?.toString() ?? 'paper';
              final status = connection['status']?.toString() ?? 'UNKNOWN';
              final account = connection['account_last4']?.toString() ?? '';
              final isConnected = status.toUpperCase() == 'CONNECTED';
              return Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: .045),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: Colors.white.withValues(alpha: .08)),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${environment.toUpperCase()} ACCOUNT${account.isEmpty ? '' : ' ••••$account'}',
                            style: const TextStyle(fontWeight: FontWeight.w800),
                          ),
                          Text(
                            isConnected ? 'Connected for market-data analysis' : status,
                            style: TextStyle(
                              fontSize: 11,
                              color: isConnected
                                  ? const Color(0xFF2DD4BF)
                                  : Colors.white60,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (isConnected)
                      TextButton(
                        onPressed: _alpacaLoading
                            ? null
                            : () => _disconnectAlpaca(environment),
                        child: const Text('Disconnect'),
                      ),
                  ],
                ),
              );
            }),
          ],
          if (!connected) ...[
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: _alpacaLoading ? null : () => _connectAlpaca('paper'),
              icon: const Icon(Icons.science_outlined),
              label: const Text('Connect Alpaca Paper'),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: _alpacaLoading ? null : () => _connectAlpaca('live'),
              icon: const Icon(Icons.account_balance_outlined),
              label: const Text('Connect Alpaca Live'),
            ),
          ] else
            OutlinedButton.icon(
              onPressed: _alpacaLoading ? null : _loadAlpacaStatus,
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('Refresh connection status'),
            ),
          const SizedBox(height: 7),
          const Text(
            'The initial Oryntra release does not submit, modify, or cancel orders.',
            style: TextStyle(fontSize: 10, color: Colors.white54),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = widget.user;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 130),
      children: [
        LiquidGlass(
          child: user == null
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      'Your Oryntra AI',
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Create an account to sync watchlists and paper trades across devices.',
                    ),
                    const SizedBox(height: 16),
                    FilledButton(
                      onPressed: () => _showAuth(create: true),
                      child: const Text('Create account'),
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton(
                      onPressed: _showAuth,
                      child: const Text('Sign in'),
                    ),
                  ],
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      user['display_name']?.toString().isNotEmpty == true
                          ? user['display_name'].toString()
                          : 'Oryntra AI user',
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w800),
                    ),
                    Text(
                      user['email']?.toString() ?? '',
                      style: const TextStyle(color: Colors.white70),
                    ),
                    const SizedBox(height: 16),
                    OutlinedButton(
                      onPressed: () async {
                        await widget.api.logout();
                        await widget.notifications.clearMarketAlerts();
                        widget.onAuthChanged();
                      },
                      child: const Text('Sign out'),
                    ),
                  ],
                ),
        ),
        const SizedBox(height: 14),
        if (user != null) _buildAlpacaCard(context),
        if (user != null) const SizedBox(height: 14),
        AppCard(
          padding: EdgeInsets.zero,
          child: Column(
            children: [
              SwitchListTile.adaptive(
                secondary: const Icon(Icons.notifications_outlined),
                title: const Text('Notifications'),
                subtitle: Text('Permission: $_notificationStatus'),
                value: _notificationsEnabled,
                onChanged: _toggleNotifications,
              ),
              const Divider(height: 1),
              SwitchListTile.adaptive(
                secondary: const Icon(Icons.schedule_outlined),
                title: const Text('Daily market reminder'),
                subtitle: const Text('Weekdays at the 9:30 AM ET market open'),
                value: _dailyReminderEnabled,
                onChanged: _notificationsEnabled
                    ? (v) async {
                        await widget.notifications.setDailyReminder(v);
                        await _loadNotificationSettings();
                      }
                    : null,
              ),
            ],
          ),
        ),
        if (user != null)
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      Icons.notifications_active_outlined,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                    const SizedBox(width: 10),
                    const Expanded(
                      child: Text(
                        'Stock market alerts',
                        style: TextStyle(fontWeight: FontWeight.w800),
                      ),
                    ),
                    Text(
                      '${_marketAlerts.length}/${NotificationService.marketAlertLimit}',
                      style: const TextStyle(color: Colors.white70),
                    ),
                  ],
                ),
                const SizedBox(height: 7),
                const Text(
                  'Choose stocks after scanning. Reminders run at 9:35 AM, noon, and 4:00 PM ET on weekdays.',
                  style: TextStyle(fontSize: 12, color: Colors.white70),
                ),
                const SizedBox(height: 12),
                if (_marketAlerts.isEmpty)
                  const Text(
                    'No stocks selected yet.',
                    style: TextStyle(color: Colors.white60),
                  )
                else
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: _marketAlerts
                        .map(
                          (ticker) => InputChip(
                            label: Text(ticker),
                            onDeleted: () => _removeMarketAlert(ticker),
                          ),
                        )
                        .toList(),
                  ),
              ],
            ),
          ),
        AppCard(
          padding: EdgeInsets.zero,
          child: Column(
            children: [
              ListTile(
                leading: const Icon(Icons.privacy_tip_outlined),
                title: const Text('Privacy choices'),
                onTap: widget.consent.showPrivacyOptions,
              ),
              ListTile(
                leading: const Icon(Icons.policy_outlined),
                title: const Text('Privacy policy'),
                onTap: () => _open(AppConfig.privacyUrl),
              ),
              ListTile(
                leading: const Icon(Icons.description_outlined),
                title: const Text('Terms of service'),
                onTap: () => _open(AppConfig.termsUrl),
              ),
              ListTile(
                leading: const Icon(Icons.warning_amber_outlined),
                title: const Text('Risk disclaimer'),
                onTap: () => _open(AppConfig.riskUrl),
              ),
              ListTile(
                leading: const Icon(Icons.science_outlined),
                title: const Text('Methodology'),
                onTap: () => _open(AppConfig.methodologyUrl),
              ),
              ListTile(
                leading: const Icon(Icons.support_agent),
                title: const Text('Contact'),
                onTap: () => _open(AppConfig.contactUrl),
              ),
            ],
          ),
        ),
        if (user != null)
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Account controls',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                TextButton.icon(
                  onPressed: _deleteAccount,
                  icon: const Icon(Icons.delete_forever_outlined),
                  label: const Text('Delete account permanently'),
                  style: TextButton.styleFrom(
                    foregroundColor: Theme.of(context).colorScheme.error,
                  ),
                ),
              ],
            ),
          ),
        Padding(
          padding: const EdgeInsets.all(20),
          child: Text(
            'Educational analysis and simulated paper trading only. Alpaca Connect is read-only for user-authorized market data; Oryntra does not place trades or provide financial advice.\nOryntra AI v${AppConfig.appVersion}${AppConfig.previewMode ? ' · browser preview' : ''}',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 12, color: Colors.white60),
          ),
        ),
      ],
    );
  }
}

class _AuthSheet extends StatefulWidget {
  const _AuthSheet({required this.api, required this.create});
  final ApiService api;
  final bool create;
  @override
  State<_AuthSheet> createState() => _AuthSheetState();
}

class _AuthSheetState extends State<_AuthSheet> {
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _loading = false;
  String? _error;

  Future<void> _submit() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (widget.create) {
        await widget.api.signup(
          _email.text.trim(),
          _password.text,
          _name.text.trim(),
        );
      } else {
        await widget.api.login(_email.text.trim(), _password.text);
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        12,
        12,
        12,
        MediaQuery.viewInsetsOf(context).bottom + 12,
      ),
      child: LiquidGlass(
        opacity: .94,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.create ? 'Create account' : 'Sign in',
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 14),
            if (widget.create) ...[
              TextField(
                controller: _name,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(labelText: 'Display name'),
              ),
              const SizedBox(height: 10),
            ],
            TextField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [AutofillHints.email],
              decoration: const InputDecoration(labelText: 'Email'),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _password,
              obscureText: true,
              autofillHints: [
                widget.create
                    ? AutofillHints.newPassword
                    : AutofillHints.password,
              ],
              decoration: InputDecoration(
                labelText: widget.create
                    ? 'Password (8+ characters)'
                    : 'Password',
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _loading ? null : _submit,
              child: Text(
                _loading
                    ? 'Please wait…'
                    : (widget.create ? 'Create account' : 'Sign in'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
