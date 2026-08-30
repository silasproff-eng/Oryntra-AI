import 'package:flutter/material.dart';
import 'glass.dart';

class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
  });
  final Widget child;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    final colors = OryntraColors.of(context);
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
      decoration: BoxDecoration(
        color: colors.panel.withValues(alpha: .93),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: colors.rule),
        boxShadow: const [
          BoxShadow(
            color: Color(0x3D000000),
            blurRadius: 18,
            offset: Offset(0, 8),
          ),
        ],
      ),
      child: Padding(padding: padding, child: child),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.body,
  });
  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    final colors = OryntraColors.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 46, color: colors.blueBright),
            const SizedBox(height: 14),
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(body, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

class AccountRequiredState extends StatelessWidget {
  const AccountRequiredState({
    super.key,
    required this.feature,
    required this.onCreateAccount,
  });

  final String feature;
  final VoidCallback onCreateAccount;

  @override
  Widget build(BuildContext context) {
    final colors = OryntraColors.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 28, 16, 130),
      children: [
        AppCard(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 24),
            child: Column(
              children: [
                Icon(
                  Icons.lock_person_outlined,
                  size: 54,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(height: 16),
                Text(
                  'Create an account to use $feature',
                  textAlign: TextAlign.center,
                  style: Theme.of(
                    context,
                  ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 8),
                Text(
                  'Your information stays connected to your Oryntra AI account and syncs across signed-in devices.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: colors.muted, height: 1.45),
                ),
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: onCreateAccount,
                    child: const Text('Create account'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class InstitutionalSectionLabel extends StatelessWidget {
  const InstitutionalSectionLabel({
    super.key,
    required this.label,
    this.trailing,
  });

  final String label;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final colors = OryntraColors.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 19, 20, 5),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label.toUpperCase(),
              style: TextStyle(
                color: colors.blueBright,
                fontSize: 11,
                letterSpacing: 1.25,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          if (trailing case final Widget trailingWidget) trailingWidget,
        ],
      ),
    );
  }
}
