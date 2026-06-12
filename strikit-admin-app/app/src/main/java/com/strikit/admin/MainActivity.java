package com.strikit.admin;

import android.content.DialogInterface;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.google.android.material.bottomnavigation.BottomNavigationView;
import com.google.android.material.chip.ChipGroup;
import com.strikit.admin.adapter.OwnerAdapter;
import com.strikit.admin.adapter.PayoutAdapter;
import com.strikit.admin.model.AdminStats;
import com.strikit.admin.model.Owner;
import com.strikit.admin.model.Payout;
import com.strikit.admin.model.PayoutRetryResponse;
import com.strikit.admin.model.TelegramWebhookResponse;
import com.strikit.admin.network.ApiClient;
import com.strikit.admin.network.ApiService;

import java.util.ArrayList;
import java.util.List;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class MainActivity extends AppCompatActivity implements 
        OwnerAdapter.OnOwnerActionListener, 
        PayoutAdapter.OnPayoutActionListener {

    // Common UI
    private ProgressBar loader;
    private TextView tvEmptyState;
    private ImageButton btnSettings;
    private BottomNavigationView bottomNav;
    private ApiService apiService;

    // TAB 1: Owners Section
    private LinearLayout layoutOwners;
    private EditText etSearch;
    private ImageButton btnClearSearch;
    private RecyclerView rvOwners;
    private OwnerAdapter ownerAdapter;
    private TextView tvStatActive, tvStatPending, tvStatFailedPayouts;
    
    private Handler searchHandler = new Handler(Looper.getMainLooper());
    private Runnable searchRunnable;

    // TAB 2: Payouts Section
    private LinearLayout layoutPayouts;
    private ChipGroup chipGroupPayoutStatus;
    private RecyclerView rvPayouts;
    private PayoutAdapter payoutAdapter;

    // TAB 3: Telegram Settings Section
    private ScrollView layoutTelegram;
    private EditText etSettingsUrl;
    private EditText etSettingsKey;
    private Button btnSaveSettings;
    private Button btnSetupTelegramWebhook;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // Bind Common Views
        loader = findViewById(R.id.loader);
        tvEmptyState = findViewById(R.id.tvEmptyState);
        btnSettings = findViewById(R.id.btnSettings);
        bottomNav = findViewById(R.id.bottomNav);

        // Bind TAB 1: Owners
        layoutOwners = findViewById(R.id.layoutOwners);
        etSearch = findViewById(R.id.etSearch);
        btnClearSearch = findViewById(R.id.btnClearSearch);
        rvOwners = findViewById(R.id.rvOwners);
        tvStatActive = findViewById(R.id.tvStatActive);
        tvStatPending = findViewById(R.id.tvStatPending);
        tvStatFailedPayouts = findViewById(R.id.tvStatFailedPayouts);

        // Bind TAB 2: Payouts
        layoutPayouts = findViewById(R.id.layoutPayouts);
        chipGroupPayoutStatus = findViewById(R.id.chipGroupPayoutStatus);
        rvPayouts = findViewById(R.id.rvPayouts);

        // Bind TAB 3: Telegram Settings
        layoutTelegram = findViewById(R.id.layoutTelegram);
        etSettingsUrl = findViewById(R.id.etSettingsUrl);
        etSettingsKey = findViewById(R.id.etSettingsKey);
        btnSaveSettings = findViewById(R.id.btnSaveSettings);
        btnSetupTelegramWebhook = findViewById(R.id.btnSetupTelegramWebhook);

        // Initialize API Service
        apiService = ApiClient.getApiService(this);

        // Setup Owners RecyclerView
        rvOwners.setLayoutManager(new LinearLayoutManager(this));
        ownerAdapter = new OwnerAdapter(this, this);
        rvOwners.setAdapter(ownerAdapter);

        // Setup Payouts RecyclerView
        rvPayouts.setLayoutManager(new LinearLayoutManager(this));
        payoutAdapter = new PayoutAdapter(this, this);
        rvPayouts.setAdapter(payoutAdapter);

        // Fetch initial list & stats
        fetchOwners("");
        fetchStats();

        // Search Input Listener (Debounced search)
        etSearch.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {}

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                if (s.length() > 0) {
                    btnClearSearch.setVisibility(View.VISIBLE);
                } else {
                    btnClearSearch.setVisibility(View.GONE);
                }

                searchHandler.removeCallbacks(searchRunnable);
                searchRunnable = () -> fetchOwners(s.toString().trim());
                searchHandler.postDelayed(searchRunnable, 500);
            }

            @Override
            public void afterTextChanged(Editable s) {}
        });

        // Clear Search Button
        btnClearSearch.setOnClickListener(v -> {
            etSearch.setText("");
            fetchOwners("");
        });

        // Top Header Settings Button -> Switches to Tab 3
        btnSettings.setOnClickListener(v -> {
            bottomNav.setSelectedItemId(R.id.nav_telegram);
        });

        // Bottom Navigation Selector
        bottomNav.setOnItemSelectedListener(item -> {
            int itemId = item.getItemId();
            if (itemId == R.id.nav_owners) {
                showTab(1);
                fetchOwners(etSearch.getText().toString().trim());
                fetchStats();
                return true;
            } else if (itemId == R.id.nav_payouts) {
                showTab(2);
                loadPayoutsBySelectedChip();
                return true;
            } else if (itemId == R.id.nav_telegram) {
                showTab(3);
                syncSettingsFields();
                return true;
            }
            return false;
        });

        // Payouts Chip Filter Selection
        chipGroupPayoutStatus.setOnCheckedStateChangeListener((group, checkedIds) -> {
            loadPayoutsBySelectedChip();
        });

        // Save Settings Button
        btnSaveSettings.setOnClickListener(v -> saveSettingsFromUi());

        // Setup Telegram Webhook Button
        btnSetupTelegramWebhook.setOnClickListener(v -> triggerTelegramWebhookSetup());
    }

    private void showTab(int tabIndex) {
        layoutOwners.setVisibility(tabIndex == 1 ? View.VISIBLE : View.GONE);
        layoutPayouts.setVisibility(tabIndex == 2 ? View.VISIBLE : View.GONE);
        layoutTelegram.setVisibility(tabIndex == 3 ? View.VISIBLE : View.GONE);
        tvEmptyState.setVisibility(View.GONE);
    }

    private void loadPayoutsBySelectedChip() {
        int checkedId = chipGroupPayoutStatus.getCheckedChipId();
        String status = null;
        if (checkedId == R.id.chipProcessing) {
            status = "PROCESSING";
        } else if (checkedId == R.id.chipCompleted) {
            status = "COMPLETED";
        } else if (checkedId == R.id.chipFailed) {
            status = "FAILED";
        }
        fetchPayouts(status);
    }

    private void syncSettingsFields() {
        etSettingsUrl.setText(ApiClient.getServerUrl(this));
        etSettingsKey.setText(ApiClient.getApiKey(this));
    }

    private void saveSettingsFromUi() {
        String url = etSettingsUrl.getText().toString().trim();
        String key = etSettingsKey.getText().toString().trim();

        if (url.isEmpty()) {
            Toast.makeText(this, "Server URL cannot be empty.", Toast.LENGTH_SHORT).show();
            return;
        }

        ApiClient.resetClient(this, url, key);
        apiService = ApiClient.getApiService(this);

        Toast.makeText(this, "Configuration Saved!", Toast.LENGTH_SHORT).show();
        
        // Go back to owners tab
        bottomNav.setSelectedItemId(R.id.nav_owners);
    }

    private void fetchStats() {
        apiService.getStats().enqueue(new Callback<AdminStats>() {
            @Override
            public void onResponse(Call<AdminStats> call, Response<AdminStats> response) {
                if (response.isSuccessful() && response.body() != null) {
                    AdminStats stats = response.body();
                    tvStatActive.setText(String.valueOf(stats.getActiveTurfs()));
                    tvStatPending.setText(String.valueOf(stats.getPendingVerifications()));
                    tvStatFailedPayouts.setText(String.valueOf(stats.getFailedPayouts()));
                }
            }

            @Override
            public void onFailure(Call<AdminStats> call, Throwable t) {
                // Fail silently or log
            }
        });
    }

    private void fetchOwners(String query) {
        loader.setVisibility(View.VISIBLE);
        tvEmptyState.setVisibility(View.GONE);

        apiService.getOwners(query).enqueue(new Callback<List<Owner>>() {
            @Override
            public void onResponse(Call<List<Owner>> call, Response<List<Owner>> response) {
                loader.setVisibility(View.GONE);
                if (response.isSuccessful() && response.body() != null) {
                    List<Owner> list = response.body();
                    ownerAdapter.setOwners(list);
                    if (list.isEmpty()) {
                        tvEmptyState.setText("No owners found.");
                        tvEmptyState.setVisibility(View.VISIBLE);
                    } else {
                        tvEmptyState.setVisibility(View.GONE);
                    }
                } else {
                    ownerAdapter.setOwners(new ArrayList<>());
                    if (response.code() == 401) {
                        tvEmptyState.setText("Authentication failed (401 Unauthorized).\nCheck API Key in Settings.");
                    } else {
                        tvEmptyState.setText("Server error occurred (Code: " + response.code() + ").");
                    }
                    tvEmptyState.setVisibility(View.VISIBLE);
                    Toast.makeText(MainActivity.this, "Error fetching data: " + response.code(), Toast.LENGTH_SHORT).show();
                }
            }

            @Override
            public void onFailure(Call<List<Owner>> call, Throwable t) {
                loader.setVisibility(View.GONE);
                ownerAdapter.setOwners(new ArrayList<>());
                tvEmptyState.setText("Network error.\nPlease check your server connection and URL settings.");
                tvEmptyState.setVisibility(View.VISIBLE);
                Toast.makeText(MainActivity.this, "Network error: " + t.getMessage(), Toast.LENGTH_LONG).show();
            }
        });
    }

    private void fetchPayouts(String status) {
        loader.setVisibility(View.VISIBLE);
        tvEmptyState.setVisibility(View.GONE);

        apiService.getPayouts(status).enqueue(new Callback<List<Payout>>() {
            @Override
            public void onResponse(Call<List<Payout>> call, Response<List<Payout>> response) {
                loader.setVisibility(View.GONE);
                if (response.isSuccessful() && response.body() != null) {
                    List<Payout> list = response.body();
                    payoutAdapter.setPayouts(list);
                    if (list.isEmpty()) {
                        tvEmptyState.setText("No payout records found.");
                        tvEmptyState.setVisibility(View.VISIBLE);
                    } else {
                        tvEmptyState.setVisibility(View.GONE);
                    }
                } else {
                    payoutAdapter.setPayouts(new ArrayList<>());
                    tvEmptyState.setText("Server error. Code: " + response.code());
                    tvEmptyState.setVisibility(View.VISIBLE);
                }
            }

            @Override
            public void onFailure(Call<List<Payout>> call, Throwable t) {
                loader.setVisibility(View.GONE);
                payoutAdapter.setPayouts(new ArrayList<>());
                tvEmptyState.setText("Network Error: " + t.getMessage());
                tvEmptyState.setVisibility(View.VISIBLE);
            }
        });
    }

    @Override
    public void onRetryPayout(Payout payout) {
        new AlertDialog.Builder(this)
                .setTitle("Retry Payout")
                .setMessage("Are you sure you want to execute manual payout retry for Booking #" + payout.getBookingId() + "?\n\nOwner: " + payout.getOwnerName() + "\nShare: " + payout.getOwnerShare())
                .setPositiveButton("Retry", (dialog, which) -> {
                    loader.setVisibility(View.VISIBLE);
                    apiService.retryPayout(payout.getId()).enqueue(new Callback<PayoutRetryResponse>() {
                        @Override
                        public void onResponse(Call<PayoutRetryResponse> call, Response<PayoutRetryResponse> response) {
                            loader.setVisibility(View.GONE);
                            if (response.isSuccessful() && response.body() != null) {
                                PayoutRetryResponse res = response.body();
                                String msg = res.getMessage() + "\nStatus: " + res.getStatus();
                                Toast.makeText(MainActivity.this, msg, Toast.LENGTH_LONG).show();
                                loadPayoutsBySelectedChip();
                                fetchStats();
                            } else {
                                Toast.makeText(MainActivity.this, "Failed to retry payout. Code: " + response.code(), Toast.LENGTH_LONG).show();
                            }
                        }

                        @Override
                        public void onFailure(Call<PayoutRetryResponse> call, Throwable t) {
                            loader.setVisibility(View.GONE);
                            Toast.makeText(MainActivity.this, "Network Error: " + t.getMessage(), Toast.LENGTH_LONG).show();
                        }
                    });
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    private void triggerTelegramWebhookSetup() {
        new AlertDialog.Builder(this)
                .setTitle("Register Telegram Webhook")
                .setMessage("This will request the server to register its Telegram webhook callback with Telegram API. Continue?")
                .setPositiveButton("Register", (dialog, which) -> {
                    loader.setVisibility(View.VISIBLE);
                    apiService.setupTelegramWebhook().enqueue(new Callback<TelegramWebhookResponse>() {
                        @Override
                        public void onResponse(Call<TelegramWebhookResponse> call, Response<TelegramWebhookResponse> response) {
                            loader.setVisibility(View.GONE);
                            if (response.isSuccessful() && response.body() != null) {
                                TelegramWebhookResponse res = response.body();
                                new AlertDialog.Builder(MainActivity.this)
                                        .setTitle("Webhook Registered")
                                        .setMessage("Message: " + res.getMessage() + "\n\nRegistered URL: " + res.getRegisteredUrl())
                                        .setPositiveButton("OK", null)
                                        .show();
                            } else {
                                Toast.makeText(MainActivity.this, "Registration failed. Code: " + response.code(), Toast.LENGTH_LONG).show();
                            }
                        }

                        @Override
                        public void onFailure(Call<TelegramWebhookResponse> call, Throwable t) {
                            loader.setVisibility(View.GONE);
                            Toast.makeText(MainActivity.this, "Network Error: " + t.getMessage(), Toast.LENGTH_LONG).show();
                        }
                    });
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    @Override
    public void onApprove(Owner owner) {
        new AlertDialog.Builder(this)
                .setTitle("Approve Owner")
                .setMessage(getString(R.string.approve_confirm))
                .setPositiveButton("Approve", (dialog, which) -> {
                    loader.setVisibility(View.VISIBLE);
                    apiService.approveOwner(owner.getId()).enqueue(new Callback<Void>() {
                        @Override
                        public void onResponse(Call<Void> call, Response<Void> response) {
                            loader.setVisibility(View.GONE);
                            if (response.isSuccessful()) {
                                Toast.makeText(MainActivity.this, "Owner Approved Successfully!", Toast.LENGTH_SHORT).show();
                                fetchOwners(etSearch.getText().toString().trim());
                                fetchStats();
                            } else {
                                Toast.makeText(MainActivity.this, "Failed to approve owner. Code: " + response.code(), Toast.LENGTH_LONG).show();
                            }
                        }

                        @Override
                        public void onFailure(Call<Void> call, Throwable t) {
                            loader.setVisibility(View.GONE);
                            Toast.makeText(MainActivity.this, "Network Error: " + t.getMessage(), Toast.LENGTH_LONG).show();
                        }
                    });
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    @Override
    public void onReject(Owner owner) {
        new AlertDialog.Builder(this)
                .setTitle("Deactivate Owner")
                .setMessage(getString(R.string.reject_confirm))
                .setPositiveButton("Deactivate", (dialog, which) -> {
                    loader.setVisibility(View.VISIBLE);
                    apiService.rejectOwner(owner.getId()).enqueue(new Callback<Void>() {
                        @Override
                        public void onResponse(Call<Void> call, Response<Void> response) {
                            loader.setVisibility(View.GONE);
                            if (response.isSuccessful()) {
                                Toast.makeText(MainActivity.this, "Owner Deactivated successfully.", Toast.LENGTH_SHORT).show();
                                fetchOwners(etSearch.getText().toString().trim());
                                fetchStats();
                            } else {
                                Toast.makeText(MainActivity.this, "Failed to deactivate owner. Code: " + response.code(), Toast.LENGTH_LONG).show();
                            }
                        }

                        @Override
                        public void onFailure(Call<Void> call, Throwable t) {
                            loader.setVisibility(View.GONE);
                            Toast.makeText(MainActivity.this, "Network Error: " + t.getMessage(), Toast.LENGTH_LONG).show();
                        }
                    });
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    @Override
    public void onDelete(Owner owner) {
        new AlertDialog.Builder(this)
                .setTitle("DANGER: DELETE OWNER")
                .setMessage(getString(R.string.delete_confirm))
                .setPositiveButton("DELETE ALL", (dialog, which) -> {
                    loader.setVisibility(View.VISIBLE);
                    apiService.deleteOwner(owner.getId()).enqueue(new Callback<Void>() {
                        @Override
                        public void onResponse(Call<Void> call, Response<Void> response) {
                            loader.setVisibility(View.GONE);
                            if (response.isSuccessful()) {
                                Toast.makeText(MainActivity.this, "Owner and all cascading records deleted.", Toast.LENGTH_LONG).show();
                                fetchOwners(etSearch.getText().toString().trim());
                                fetchStats();
                            } else {
                                Toast.makeText(MainActivity.this, "Failed to delete owner. Code: " + response.code(), Toast.LENGTH_LONG).show();
                            }
                        }

                        @Override
                        public void onFailure(Call<Void> call, Throwable t) {
                            loader.setVisibility(View.GONE);
                            Toast.makeText(MainActivity.this, "Network Error: " + t.getMessage(), Toast.LENGTH_LONG).show();
                        }
                    });
                })
                .setNegativeButton("Cancel", null)
                .setIcon(android.R.drawable.ic_dialog_alert)
                .show();
    }
}
