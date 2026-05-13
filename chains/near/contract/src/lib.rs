use near_sdk::borsh::{self, BorshDeserialize, BorshSerialize};
use near_sdk::collections::LookupMap;
use near_sdk::{env, near_bindgen, AccountId, Promise, require, PanicOnDefault};

#[near_bindgen]
#[derive(BorshDeserialize, BorshSerialize, PanicOnDefault)]
pub struct BTCPContract {
    relayer: AccountId,
    intents: LookupMap<String, IntentRecord>,
    escrows: LookupMap<String, EscrowRecord>,
}

#[derive(BorshDeserialize, BorshSerialize)]
pub struct IntentRecord {
    entity_id: String,
    source_chain: u64,
    dest_chain: u64,
    magnitude: u128,
    status: u8, // 0=PENDING 1=ROUTING 2=EXECUTING 3=COMPLETED 4=FAILED
}

#[derive(BorshDeserialize, BorshSerialize)]
pub struct EscrowRecord {
    entity_id: String,
    destination: AccountId,
    amount: u128,
    lock_block: u64,
    timeout_blocks: u64,
    state: u8, // 0=HOLDING 1=RELEASED 2=REVERTED
}

#[near_bindgen]
impl BTCPContract {
    #[init]
    pub fn new(relayer: AccountId) -> Self {
        Self {
            relayer,
            intents: LookupMap::new(b"i"),
            escrows: LookupMap::new(b"e"),
        }
    }

    pub fn register_intent(
        &mut self,
        intent_id: String,
        entity_id: String,
        source_chain: u64,
        dest_chain: u64,
        magnitude: u128,
    ) {
        let record = IntentRecord {
            entity_id,
            source_chain,
            dest_chain,
            magnitude,
            status: 0,
        };
        self.intents.insert(&intent_id, &record);
        env::log_str(&format!(
            "IntentRegistered:{}:{}:{}",
            intent_id, source_chain, dest_chain
        ));
    }

    #[payable]
    pub fn lock_escrow(
        &mut self,
        escrow_id: String,
        entity_id: String,
        destination: AccountId,
        timeout_blocks: u64,
    ) {
        let amount = env::attached_deposit().as_yoctonear();
        require!(amount > 0, "Must attach NEAR");
        let record = EscrowRecord {
            entity_id,
            destination,
            amount,
            lock_block: env::block_height(),
            timeout_blocks,
            state: 0,
        };
        self.escrows.insert(&escrow_id, &record);
        env::log_str(&format!("EscrowLocked:{}:{}", escrow_id, amount));
    }

    pub fn release_escrow(
        &mut self,
        escrow_id: String,
        btcp_route_id: String,
        is_safe: bool,
        coherence: u64,
        threshold: u64,
    ) -> Promise {
        require!(
            env::predecessor_account_id() == self.relayer,
            "Only relayer can release"
        );
        require!(is_safe && coherence >= threshold, "Coherence check failed");

        let mut record = self
            .escrows
            .get(&escrow_id)
            .expect("Escrow not found");
        require!(record.state == 0, "Escrow not in HOLDING state");

        record.state = 1; // RELEASED
        self.escrows.insert(&escrow_id, &record);

        env::log_str(&format!(
            "EscrowReleased:{}:{}:{}",
            escrow_id, btcp_route_id, record.amount
        ));

        Promise::new(record.destination)
            .transfer(near_sdk::NearToken::from_yoctonear(record.amount))
    }

    pub fn revert_escrow(&mut self, escrow_id: String) -> Promise {
        let mut record = self
            .escrows
            .get(&escrow_id)
            .expect("Escrow not found");
        require!(record.state == 0, "Not HOLDING");
        require!(
            env::block_height() > record.lock_block + record.timeout_blocks,
            "Timeout not reached"
        );
        record.state = 2; // REVERTED
        self.escrows.insert(&escrow_id, &record);
        env::log_str(&format!("EscrowReverted:{}", escrow_id));

        let entity = AccountId::try_from(record.entity_id)
            .unwrap_or(env::predecessor_account_id());
        Promise::new(entity)
            .transfer(near_sdk::NearToken::from_yoctonear(record.amount))
    }

    pub fn get_escrow(&self, escrow_id: String) -> Option<String> {
        self.escrows.get(&escrow_id).map(|r| {
            format!(
                "state:{}:amount:{}:dest:{}",
                r.state, r.amount, r.destination
            )
        })
    }

    pub fn get_intent(&self, intent_id: String) -> Option<String> {
        self.intents.get(&intent_id).map(|r| {
            format!(
                "status:{}:source:{}:dest:{}",
                r.status, r.source_chain, r.dest_chain
            )
        })
    }
}
