"""
Property Tests for Multi-Armed Bandit Policies

Uses Hypothesis library to test policy invariants and properties
that should hold across all possible inputs and scenarios.

Property Tests:
- UCB confidence bounds decrease monotonically with pulls
- Thompson alpha/beta parameters never decrease
- ε-greedy best arm selected ≥ (1-ε) fraction of time
- Policy state updates maintain consistency
- Reward calculations are idempotent

Usage:
    pytest backend/tests/property_tests.py -v
    hypothesis --show-statistics backend/tests/property_tests.py
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from hypothesis import given, strategies as st, settings, example
from hypothesis.strategies import integers, floats, lists, tuples, booleans
from sqlalchemy.orm import Session

# Import the modules to test
from backend.ml.policies.thompson_sampling import ThompsonSamplingPolicy
from backend.ml.policies.epsilon_greedy import EpsilonGreedyPolicy
from backend.ml.policies.ucb1 import UCB1Policy
from backend.ml.policies.base import PolicyStateStore
from backend.ml.reward_calculator import RewardCalculator

class TestPolicyProperties:
    """Property tests for bandit policies"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    @given(
        arm_id=st.text(min_size=1, max_size=10),
        context_key=st.text(min_size=1, max_size=10),
        initial_alpha=st.floats(min_value=1.0, max_value=100.0),
        initial_beta=st.floats(min_value=1.0, max_value=100.0),
        rewards=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=50)
    )
    def test_thompson_alpha_beta_monotonicity(self, mock_db, arm_id, context_key, 
                                            initial_alpha, initial_beta, rewards):
        """Property: Thompson Sampling alpha/beta parameters never decrease"""
        policy = ThompsonSamplingPolicy(mock_db)
        
        # Mock state store
        with patch.object(policy.store, 'get_state') as mock_get_state:
            mock_state = Mock()
            mock_state.alpha = initial_alpha
            mock_state.beta = initial_beta
            mock_get_state.return_value = mock_state
            
            # Apply rewards sequentially
            for reward in rewards:
                # Store initial values
                prev_alpha = mock_state.alpha
                prev_beta = mock_state.beta
                
                # Update policy
                policy.update(arm_id, reward, {})
                
                # Check monotonicity
                assert mock_state.alpha >= prev_alpha, f"Alpha decreased: {prev_alpha} -> {mock_state.alpha}"
                assert mock_state.beta >= prev_beta, f"Beta decreased: {prev_beta} -> {mock_state.beta}"
                
                # Check specific increments
                if reward > 0:
                    assert mock_state.alpha == prev_alpha + 1, f"Alpha should increment by 1 for positive reward"
                else:
                    assert mock_state.beta == prev_beta + 1, f"Beta should increment by 1 for zero reward"
    
    @given(
        epsilon=st.floats(min_value=0.01, max_value=0.5),
        num_arms=st.integers(min_value=2, max_value=10),
        num_selections=st.integers(min_value=100, max_value=1000),
        arm_rewards=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=2, max_size=10)
    )
    def test_epsilon_greedy_exploitation_rate(self, mock_db, epsilon, num_arms, 
                                            num_selections, arm_rewards):
        """Property: ε-greedy selects best arm ≥ (1-ε) fraction of time"""
        policy = EpsilonGreedyPolicy(mock_db, epsilon=epsilon)
        
        # Ensure we have enough arms
        if len(arm_rewards) < num_arms:
            arm_rewards.extend([0.0] * (num_arms - len(arm_rewards)))
        
        # Find best arm
        best_arm_idx = np.argmax(arm_rewards)
        best_arm = f"arm_{best_arm_idx}"
        arms = [f"arm_{i}" for i in range(num_arms)]
        
        # Mock state store with different rewards
        with patch.object(policy.store, 'get_state') as mock_get_state:
            def mock_get_state_side_effect(arm_id, context_key='default'):
                mock_state = Mock()
                mock_state.count = 100  # Ensure not cold start
                arm_idx = int(arm_id.split('_')[1])
                mock_state.mean_reward = arm_rewards[arm_idx]
                return mock_state
            
            mock_get_state.side_effect = mock_get_state_side_effect
            
            # Count selections
            best_arm_selections = 0
            total_selections = 0
            
            for _ in range(num_selections):
                result = policy.select({}, arms)
                if result.arm_id == best_arm:
                    best_arm_selections += 1
                total_selections += 1
            
            # Check exploitation rate
            exploitation_rate = best_arm_selections / total_selections
            expected_min_rate = 1.0 - epsilon
            
            # Allow some tolerance for randomness
            assert exploitation_rate >= expected_min_rate - 0.1, \
                f"Exploitation rate {exploitation_rate:.3f} below expected {expected_min_rate:.3f}"
    
    @given(
        total_pulls=st.integers(min_value=100, max_value=10000),
        arm_pulls=st.integers(min_value=1, max_value=1000),
        mean_reward=st.floats(min_value=0.0, max_value=1.0)
    )
    def test_ucb_confidence_bounds(self, mock_db, total_pulls, arm_pulls, mean_reward):
        """Property: UCB confidence bounds decrease monotonically with pulls"""
        policy = UCB1Policy(mock_db)
        
        # Mock state store
        with patch.object(policy.store, 'get_state') as mock_get_state:
            mock_state = Mock()
            mock_state.count = arm_pulls
            mock_state.mean_reward = mean_reward
            mock_get_state.return_value = mock_state
            
            # Calculate UCB values for different total pulls
            ucb_values = []
            for total in range(total_pulls, total_pulls + 100, 10):
                # Mock total pulls calculation
                with patch.object(policy, '_get_total_pulls', return_value=total):
                    result = policy.select({}, ['test_arm'])
                    ucb_values.append(result.confidence)
            
            # Check monotonicity (confidence should decrease as total pulls increase)
            for i in range(1, len(ucb_values)):
                assert ucb_values[i] <= ucb_values[i-1], \
                    f"UCB confidence increased: {ucb_values[i-1]:.3f} -> {ucb_values[i]:.3f}"
    
    @given(
        arm_id=st.text(min_size=1, max_size=10),
        context_key=st.text(min_size=1, max_size=10),
        rewards=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=20)
    )
    def test_policy_state_consistency(self, mock_db, arm_id, context_key, rewards):
        """Property: Policy state updates maintain mathematical consistency"""
        state_store = PolicyStateStore(mock_db, "test_policy")
        
        # Mock state
        mock_state = Mock()
        mock_state.count = 0
        mock_state.sum_reward = 0.0
        mock_state.mean_reward = 0.0
        mock_state.alpha = 1.0
        mock_state.beta = 1.0
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_state
        
        # Apply rewards sequentially
        for reward in rewards:
            # Store previous values
            prev_count = mock_state.count
            prev_sum = mock_state.sum_reward
            prev_mean = mock_state.mean_reward
            prev_alpha = mock_state.alpha
            prev_beta = mock_state.beta
            
            # Update state
            state_store.update_state(arm_id, reward, context_key)
            
            # Check consistency
            assert mock_state.count == prev_count + 1, "Count should increment by 1"
            assert mock_state.sum_reward == prev_sum + reward, "Sum should increase by reward"
            assert mock_state.mean_reward == mock_state.sum_reward / mock_state.count, "Mean should be sum/count"
            
            # Check Thompson parameters
            if reward > 0:
                assert mock_state.alpha == prev_alpha + 1, "Alpha should increment for positive reward"
                assert mock_state.beta == prev_beta, "Beta should not change for positive reward"
            else:
                assert mock_state.alpha == prev_alpha, "Alpha should not change for zero reward"
                assert mock_state.beta == prev_beta + 1, "Beta should increment for zero reward"
    
    @given(
        served_at=st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2023, 12, 31)),
        clicked=st.booleans(),
        rated=st.booleans(),
        thumbs_up=st.booleans(),
        added_to_watchlist=st.booleans(),
        added_to_favorites=st.booleans(),
        rating_value=st.floats(min_value=1.0, max_value=5.0) | st.none()
    )
    def test_reward_calculator_idempotency(self, mock_db, served_at, clicked, rated, 
                                         thumbs_up, added_to_watchlist, added_to_favorites, rating_value):
        """Property: Reward calculation is idempotent"""
        reward_calculator = RewardCalculator(mock_db, reward_window_hours=24)
        
        # Create mock event
        event = Mock()
        event.served_at = served_at
        event.clicked = clicked
        event.clicked_at = served_at + timedelta(minutes=5) if clicked else None
        event.rated = rated
        event.rated_at = served_at + timedelta(minutes=10) if rated else None
        event.rating_value = rating_value
        event.thumbs_up = thumbs_up
        event.thumbs_up_at = served_at + timedelta(minutes=15) if thumbs_up else None
        event.added_to_watchlist = added_to_watchlist
        event.added_to_favorites = added_to_favorites
        event.created_at = served_at + timedelta(minutes=20)
        
        # Calculate reward multiple times
        reward1 = reward_calculator.compute_reward(event)
        reward2 = reward_calculator.compute_reward(event)
        reward3 = reward_calculator.compute_reward(event)
        
        # Should be idempotent
        assert reward1 == reward2 == reward3, f"Reward calculation not idempotent: {reward1} != {reward2} != {reward3}"
    
    @given(
        num_arms=st.integers(min_value=2, max_value=20),
        num_selections=st.integers(min_value=50, max_value=500),
        arm_rewards=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=2, max_size=20)
    )
    def test_policy_selection_validity(self, mock_db, num_arms, num_selections, arm_rewards):
        """Property: Policy selections are always valid"""
        policies = [
            ThompsonSamplingPolicy(mock_db),
            EpsilonGreedyPolicy(mock_db, epsilon=0.1),
            UCB1Policy(mock_db)
        ]
        
        # Ensure we have enough arms
        if len(arm_rewards) < num_arms:
            arm_rewards.extend([0.0] * (num_arms - len(arm_rewards)))
        
        arms = [f"arm_{i}" for i in range(num_arms)]
        context = {'user_type': 'test'}
        
        for policy in policies:
            # Mock state store
            with patch.object(policy.store, 'get_state') as mock_get_state:
                def mock_get_state_side_effect(arm_id, context_key='default'):
                    mock_state = Mock()
                    mock_state.count = 100  # Ensure not cold start
                    arm_idx = int(arm_id.split('_')[1])
                    mock_state.mean_reward = arm_rewards[arm_idx]
                    mock_state.alpha = 5.0
                    mock_state.beta = 5.0
                    return mock_state
                
                mock_get_state.side_effect = mock_get_state_side_effect
                
                # Test multiple selections
                for _ in range(num_selections):
                    result = policy.select(context, arms)
                    
                    # Check validity
                    assert result.arm_id in arms, f"Selected arm {result.arm_id} not in available arms {arms}"
                    assert result.confidence >= 0.0, f"Confidence {result.confidence} is negative"
                    if result.p_score is not None:
                        assert 0.0 <= result.p_score <= 1.0, f"P-score {result.p_score} not in [0,1]"
    
    @given(
        epsilon=st.floats(min_value=0.01, max_value=0.5),
        num_arms=st.integers(min_value=2, max_value=10)
    )
    def test_epsilon_greedy_propensity_scores(self, mock_db, epsilon, num_arms):
        """Property: ε-greedy propensity scores sum to 1.0"""
        policy = EpsilonGreedyPolicy(mock_db, epsilon=epsilon)
        
        arms = [f"arm_{i}" for i in range(num_arms)]
        context = {'user_type': 'test'}
        
        # Mock state store with equal rewards (tie scenario)
        with patch.object(policy.store, 'get_state') as mock_get_state:
            mock_state = Mock()
            mock_state.count = 100
            mock_state.mean_reward = 0.5  # Same for all arms
            mock_get_state.return_value = mock_state
            
            # Calculate propensity scores for all arms
            propensity_scores = []
            for arm in arms:
                result = policy.select(context, arms)
                if result.arm_id == arm and result.p_score is not None:
                    propensity_scores.append(result.p_score)
            
            # In tie scenario, all arms should have equal probability
            if propensity_scores:
                expected_prob = 1.0 / num_arms
                for p_score in propensity_scores:
                    assert abs(p_score - expected_prob) < 0.01, \
                        f"Propensity score {p_score} not equal to expected {expected_prob}"
    
    @given(
        num_updates=st.integers(min_value=1, max_value=100),
        rewards=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=100)
    )
    def test_state_update_convergence(self, mock_db, num_updates, rewards):
        """Property: State updates converge to true mean"""
        state_store = PolicyStateStore(mock_db, "test_policy")
        
        # Mock state
        mock_state = Mock()
        mock_state.count = 0
        mock_state.sum_reward = 0.0
        mock_state.mean_reward = 0.0
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_state
        
        # Apply rewards
        for reward in rewards[:num_updates]:
            state_store.update_state("test_arm", reward, "default")
        
        # Check convergence
        true_mean = sum(rewards[:num_updates]) / num_updates
        assert abs(mock_state.mean_reward - true_mean) < 1e-10, \
            f"Mean reward {mock_state.mean_reward} not equal to true mean {true_mean}"
        
        assert mock_state.count == num_updates, f"Count {mock_state.count} not equal to updates {num_updates}"
        assert abs(mock_state.sum_reward - sum(rewards[:num_updates])) < 1e-10, \
            f"Sum reward {mock_state.sum_reward} not equal to true sum {sum(rewards[:num_updates])}"

class TestEdgeCases:
    """Edge case tests for policies"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    def test_empty_arms_list(self, mock_db):
        """Test handling of empty arms list"""
        policy = ThompsonSamplingPolicy(mock_db)
        
        with pytest.raises(ValueError):
            policy.select({}, [])
    
    def test_single_arm(self, mock_db):
        """Test handling of single arm"""
        policy = ThompsonSamplingPolicy(mock_db)
        
        with patch.object(policy.store, 'get_state') as mock_get_state:
            mock_state = Mock()
            mock_state.alpha = 1.0
            mock_state.beta = 1.0
            mock_get_state.return_value = mock_state
            
            result = policy.select({}, ['single_arm'])
            assert result.arm_id == 'single_arm'
            assert result.p_score == 1.0
    
    def test_zero_reward(self, mock_db):
        """Test handling of zero reward"""
        state_store = PolicyStateStore(mock_db, "test_policy")
        
        mock_state = Mock()
        mock_state.count = 10
        mock_state.sum_reward = 5.0
        mock_state.mean_reward = 0.5
        mock_state.alpha = 5.0
        mock_state.beta = 5.0
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_state
        
        state_store.update_state("test_arm", 0.0, "default")
        
        assert mock_state.count == 11
        assert mock_state.sum_reward == 5.0
        assert mock_state.mean_reward == 5.0 / 11
        assert mock_state.alpha == 5.0
        assert mock_state.beta == 6.0
    
    def test_negative_reward(self, mock_db):
        """Test handling of negative reward (should not happen in practice)"""
        state_store = PolicyStateStore(mock_db, "test_policy")
        
        mock_state = Mock()
        mock_state.count = 10
        mock_state.sum_reward = 5.0
        mock_state.mean_reward = 0.5
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_state
        
        # Should handle negative rewards gracefully
        state_store.update_state("test_arm", -0.5, "default")
        
        assert mock_state.count == 11
        assert mock_state.sum_reward == 4.5
        assert mock_state.mean_reward == 4.5 / 11

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
