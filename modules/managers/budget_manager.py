# modules/managers/budget_manager.py

class BudgetManager:
    """
    Manages budget-related validations and calculations.
    """

    def __init__(self):
        pass

    def validate_budget_allocations(self, config_data: dict) -> list:
        """
        Validates that allocated amounts within budget scopes and sub-budgets
        are correctly distributed. Returns a list of alarm/warning/note messages.
        """
        messages = []  # Change to messages, not alarms

        # Validate top-level budget scopes (Family, Personal)
        budget_scopes = config_data.get('budget_scopes', [])
        for scope_name in budget_scopes:
            scope_data = config_data.get(scope_name, {})
            allocated_amount = scope_data.get('allocated')
            budget_items = scope_data.get('budget', {})

            if allocated_amount is None:
                messages.append({'type': 'warning',
                                 'message': f"'{scope_name}' budget has no 'allocated' amount defined. Cannot fully validate."})
                continue

            # Calculate sum of direct categories and sub-budgets
            current_sum = 0.0
            for cat_name, cat_details in budget_items.items():
                if 'budget' in cat_details and isinstance(cat_details.get('budget'), dict):
                    # This is a nested budget (e.g., 'Businesses' under 'Personal')
                    sub_allocated = cat_details.get('allocated')
                    if sub_allocated is None:
                        messages.append({'type': 'warning',
                                         'message': f"Sub-budget '{cat_name}' under '{scope_name}' has no 'allocated' amount defined. Cannot fully validate its sub-items."})
                        # If no allocated amount, we can't check its sum against anything
                        # We'll just sum its sub-items if they have amounts
                        sub_sum = sum(item.get('amount', 0.0) for item in cat_details['budget'].values() if
                                      isinstance(item, dict))
                        if sub_sum > 0:
                            messages.append({'type': 'note',
                                             'message': f"Sub-budget '{cat_name}' under '{scope_name}' has no 'allocated' amount. Sum of its sub-categories is {sub_sum:.2f}."})
                        current_sum += sub_sum  # Add what it sums to for its parent check
                    else:
                        current_sum += sub_allocated
                        # Recursively validate sub-budget
                        nested_messages = self._validate_nested_budget(cat_name, cat_details)
                        if nested_messages:
                            messages.extend(nested_messages)
                elif isinstance(cat_details, dict) and 'amount' in cat_details:
                    current_sum += cat_details.get('amount', 0.0)
                else:
                    messages.append({'type': 'warning',
                                     'message': f"Category '{cat_name}' under '{scope_name}' has an invalid structure or missing 'amount'."})

            # Check if the sum of budget items exceeds allocated amount
            if current_sum > allocated_amount:
                messages.append({'type': 'alarm',
                                 'message': f"'{scope_name}' budget allocation discrepancy! Sum of categories ({current_sum:.2f}) exceeds allocated amount ({allocated_amount:.2f}). **Action Required!**"})
            elif current_sum < allocated_amount:
                messages.append({'type': 'note',
                                 'message': f"'{scope_name}' budget allocation has unallocated funds. Sum of categories ({current_sum:.2f}) is less than allocated amount ({allocated_amount:.2f})."})

        return messages

    def _validate_nested_budget(self, budget_name: str, budget_data: dict) -> list:
        """
        Helper function to recursively validate nested budgets (like 'Businesses').
        Returns a list of alarm/warning/note messages.
        """
        messages = []
        allocated_amount = budget_data.get('allocated')
        budget_items = budget_data.get('budget', {})
        # budget_name = budget_data.get('name', 'Nested Budget')  # For better message context

        if allocated_amount is None:
            # messages.append({'type': 'warning', 'message': f"Nested budget '{budget_name}' has no 'allocated' amount defined. Cannot fully validate."})
            return messages  # If no allocated amount, can't check its sum against anything, return early for this branch

        current_sum = 0.0
        for item_name, item_details in budget_items.items():
            if 'template' in item_details:  # This is a specific business using a template
                # Check template-based budget items
                template_budget = item_details.get('budget', {})
                template_allocated = item_details.get('allocated')

                if template_allocated is not None:
                    current_sum += template_allocated  # Add the business's allocated amount to its parent sum
                    sub_sum = sum(sub_item.get('amount', 0.0) for sub_item in template_budget.values() if
                                  isinstance(sub_item, dict))
                    if sub_sum > template_allocated:
                        messages.append({'type': 'alarm',
                                         'message': f"Business budget '{item_name}' allocation discrepancy! Sum of categories ({sub_sum:.2f}) exceeds allocated amount ({template_allocated:.2f}). **Action Required!**"})
                    elif sub_sum < template_allocated:
                        messages.append({'type': 'note',
                                         'message': f"Business budget '{item_name}' has unallocated funds. Sum of categories ({sub_sum:.2f}) is less than allocated amount ({template_allocated:.2f})."})
                else:
                    # If template_allocated is None for a business, just sum up the explicit amounts
                    # and add to parent sum, no internal check possible against 'allocated'
                    sum_of_template_items = sum(sub_item.get('amount', 0.0) for sub_item in template_budget.values() if
                                                isinstance(sub_item, dict))
                    current_sum += sum_of_template_items
                    if sum_of_template_items > 0:  # Only if it actually contributes something
                        messages.append({'type': 'note',
                                         'message': f"Business budget '{item_name}' has no 'allocated' amount. Sum of its sub-categories is {sum_of_template_items:.2f}."})

            elif isinstance(item_details, dict) and 'amount' in item_details:
                current_sum += item_details.get('amount', 0.0)
            elif isinstance(item_details, dict) and 'budget' in item_details:  # Another nested budget level
                sub_allocated = item_details.get('allocated')
                if sub_allocated is not None:
                    current_sum += sub_allocated
                else:
                    # If a nested budget without 'allocated' amount, just sum its parts to contribute
                    sum_of_nested_items = sum(
                        sub_item.get('amount', 0.0) for sub_item in item_details.get('budget', {}).values() if
                        isinstance(sub_item, dict))
                    current_sum += sum_of_nested_items
                    if sum_of_nested_items > 0:
                        messages.append({'type': 'note',
                                         'message': f"Nested budget '{item_name}' under '{budget_name}' has no 'allocated' amount. Sum of its sub-categories is {sum_of_nested_items:.2f}."})

                # Recursively validate deeper nested budgets
                messages.extend(self._validate_nested_budget(item_name, item_details))
            else:
                messages.append({'type': 'warning',
                                 'message': f"Item '{item_name}' under '{budget_name}' has an invalid structure or missing 'amount/budget'."})

        if allocated_amount is not None:  # Only check against allocated if it exists
            if current_sum > allocated_amount:
                messages.append({'type': 'alarm',
                                 'message': f"Nested budget '{budget_name}' allocation discrepancy! Sum of items ({current_sum:.2f}) exceeds allocated amount ({allocated_amount:.2f}). **Action Required!**"})
            elif current_sum < allocated_amount:
                messages.append({'type': 'note',
                                 'message': f"Nested budget '{budget_name}' has unallocated funds. Sum of items ({current_sum:.2f}) is less than allocated amount ({allocated_amount:.2f})."})

        return messages