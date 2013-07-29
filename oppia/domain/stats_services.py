# coding: utf-8
#
# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Services for Oppia statistics."""

__author__ = 'Sean Lip'

import feconf
from oppia.domain import exp_domain
from oppia.domain import stats_domain
import oppia.storage.state.models as state_models
import oppia.storage.statistics.models as stats_models


IMPROVE_TYPE_DEFAULT = 'default'
IMPROVE_TYPE_INCOMPLETE = 'incomplete'


class EventHandler(object):
    """Records events."""

    @classmethod
    def record_state_hit(cls, exploration_id, state_id, first_time):
        """Record an event when a state is encountered by the reader."""
        stats_models.StateCounterModel.inc(
            exploration_id, state_id, first_time)

    @classmethod
    def record_answer_submitted(cls, exploration_id, state_id, rule, answer):
        """Records an event when an answer triggers a rule."""
        stats_models.process_submitted_answer(
            exploration_id, state_id, rule, answer)

    @classmethod
    def resolve_answers_for_default_rule(
            cls, exploration_id, state_id, answers):
        stats_models.resolve_answers(
            exploration_id, state_id,
            state_models.DEFAULT_RULESPEC_STR, answers)


def get_unresolved_answers_for_default_rule(exploration_id, state_id):
    """Gets the tally of unresolved answers that hit the default rule."""
    # TODO(sll): Add similar functionality for other rules.
    # TODO(sll): Should this return just the top N answers instead?
    return stats_domain.StateRuleAnswerLog.get(
        exploration_id, state_id, state_models.DEFAULT_RULESPEC_STR).answers


def export_exploration_stats_to_dict(exploration_id):
    """Returns a dict with stats for the given exploration id."""
    exploration = exp_domain.Exploration.get(exploration_id)

    num_visits = stats_domain.StateCounter.get(
        exploration_id, exploration.init_state_id).first_entry_count
    # Note that the subsequent_entries_count for END_DEST should be 0.
    num_completions = stats_domain.StateCounter.get(
        exploration_id, feconf.END_DEST).first_entry_count

    answers = {}
    for state_id in exploration.state_ids:
        # TODO(sll): Remove this call.
        state = exploration.get_state_by_id(state_id)
        answers[state.id] = {
            'name': state.name,
            'rules': {}
        }
        for handler in state.widget.handlers:
            for rule in handler.rule_specs:
                answer_log = stats_domain.StateRuleAnswerLog.get(
                    exploration_id, state.id, str(rule))

                answers[state.id]['rules'][str(rule)] = {
                    'answers': answer_log.get_top_answers(10)
                }

    state_counts = {}
    for state_id in exploration.state_ids:
        # TODO(sll): Remove this call.
        state = exploration.get_state_by_id(state_id)
        state_counts[state_id] = {
            'name': state.name,
            'count': stats_domain.StateCounter.get(
                exploration_id, state_id).total_entry_count,
        }

    state_stats = {}
    for state_id in answers:
        all_rule_count = 0
        state_count = state_counts[state_id]['count']

        rule_stats = {}
        for rule in answers[state_id]['rules']:
            # TODO(sll): Can this computation be done in the frontend instead?
            rule_count = 0
            for _, count in answers[state_id]['rules'][rule]['answers']:
                rule_count += count
                all_rule_count += count

            rule_stats[rule] = answers[state_id]['rules'][rule]
            rule_stats[rule]['chartData'] = [
                ['', 'This rule', 'Other answers'],
                ['', rule_count, state_count - rule_count]]

        state_stats[state_id] = {
            'name': answers[state_id]['name'],
            'count': state_count,
            'rule_stats': rule_stats,
            'no_answer_chartdata': [
                ['', 'No answer', 'Answer given'],
                ['',  state_count - all_rule_count, all_rule_count]
            ]
        }

    return {
        'num_visits': num_visits,
        'num_completions': num_completions,
        'state_stats': state_stats,
    }


def get_top_improvable_states(exploration_ids, N):
    """Returns the top N improvable states across all the given explorations."""

    ranked_states = []
    for exploration_id in exploration_ids:
        exploration = exp_domain.Exploration.get(exploration_id)
        for state_id in exploration.state_ids:
            state_counts = stats_domain.StateCounter.get(
                exploration_id, state_id)
            default_rule_answer_log = stats_domain.StateRuleAnswerLog.get(
                exploration.id, state_id, state_models.DEFAULT_RULESPEC_STR)

            total_entry_count = state_counts.total_entry_count
            if total_entry_count == 0:
                continue

            default_count = default_rule_answer_log.total_answer_count
            no_answer_submitted_count = state_counts.no_answer_count

            eligible_flags = []

            state = exploration.get_state_by_id(state_id)
            if (default_count > 0.2 * total_entry_count and
                    state.widget.handlers[0].default_rule_spec.dest ==
                    state.id):
                eligible_flags.append({
                    'rank': default_count,
                    'improve_type': IMPROVE_TYPE_DEFAULT})

            if no_answer_submitted_count > 0.2 * total_entry_count:
                eligible_flags.append({
                    'rank': no_answer_submitted_count,
                    'improve_type': IMPROVE_TYPE_INCOMPLETE})

            state_rank, improve_type = 0, ''
            if eligible_flags:
                eligible_flags = sorted(
                    eligible_flags, key=lambda flag: flag['rank'],
                    reverse=True)
                state_rank = eligible_flags[0]['rank']
                improve_type = eligible_flags[0]['improve_type']

            ranked_states.append({
                'exp_id': exploration_id,
                'exp_name': exploration.title,
                'state_id': state_id,
                'state_name': state.name,
                'rank': state_rank,
                'type': improve_type,
                'top_default_answers': default_rule_answer_log.get_top_answers(
                    5)
            })

    problem_states = sorted(
        [state for state in ranked_states if state['rank'] != 0],
        key=lambda state: state['rank'],
        reverse=True)
    return problem_states[:N]


def delete_all_stats():
    """Deletes all statistics."""
    stats_models.delete_all_stats()
